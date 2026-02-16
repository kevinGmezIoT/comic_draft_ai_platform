import os
import json
import requests
import boto3
from dotenv import load_dotenv
from core.graph import create_comic_graph
from bedrock_agentcore.runtime import BedrockAgentCoreApp

load_dotenv(override=True)

# Initialize Bedrock Agent Core App
app = BedrockAgentCoreApp()

# SQS Client for results notification
sqs = boto3.client('sqs', region_name=os.getenv('AWS_REGION', 'us-east-1'))
queue_url = os.getenv('AWS_SQS_QUEUE_URL')

# Compile the LangGraph
graph = create_comic_graph()

def notify_completion(project_id, result, action):
    """Notify backend via SQS upon task completion or failure."""
    if not queue_url:
        print(f"WARNING: AWS_SQS_QUEUE_URL not set. Action '{action}' results will not be sent.")
        return

    print(f"DEBUG: Notifying completion for action '{action}' on project {project_id}")
    try:
        message_body = json.dumps({
            "project_id": project_id,
            "status": "completed" if "error" not in result else "failed",
            "action": action,
            "result": result
        })
        sqs.send_message(QueueUrl=queue_url, MessageBody=message_body)
        print("DEBUG: SQS message sent successfully.")
    except Exception as e:
        print(f"ERROR: Failed to send SQS message: {e}")

def generate_comic_logic(project_id, sources, max_pages=3, max_panels=None, layout_style="dynamic", **kwargs):
    """
    Core logic for initial comic generation.
    """
    print(f"--- GENERATING COMIC: Project {project_id} ---")
    
    initial_state = {
        "project_id": project_id,
        "sources": sources,
        "max_pages": max_pages,
        "max_panels": max_panels,
        "layout_style": layout_style,
        "plan_only": kwargs.get("plan_only", False),
        "panels": kwargs.get("panels", []),
        "merged_pages": [],
        "world_model_summary": "",
        "script_outline": [],
        "current_step": "start",
        "reference_images": kwargs.get("reference_images", []),
        "global_context": kwargs.get("global_context", {})
    }

    try:
        # LangSmith tracing metadata
        config = {
            "configurable": {"project_id": project_id},
            "metadata": {
                "project_id": project_id,
                "action": "generate",
                "max_pages": max_pages
            },
            "tags": ["comic-generation", f"project-{project_id}"]
        }
        
        result = graph.invoke(initial_state, config=config)
        
        # Notify backend via SQS
        notify_completion(project_id, result, "generate")
            
        return result
    except Exception as e:
        print(f"Error in graph execution: {e}")
        notify_completion(project_id, {"error": str(e)}, "generate")
        return {"current_step": "error", "error": str(e)}

def regenerate_panel_logic(project_id, panel_id, prompt, scene_description, balloons, **kwargs):
    """
    Logic for single panel regeneration with enhanced context.
    """
    print(f"--- REGENERATING PANEL: {panel_id} in Project {project_id} ---")
    print(f"DEBUG: Received regeneration context: {kwargs}")
    from core.graph import image_generator
    
    # We no longer fetch from backend, we expect the context in kwargs (matched generate_comic_logic)
    all_panels = kwargs.get('panels', [])
    world_model_summary = kwargs.get('world_model_summary', "")
    global_context = kwargs.get('global_context', {})
    
    # Pre-process panels to ensure format is consistent with AgentState
    processed_panels = []
    for p in all_panels:
        # If it's the target panel, update with latest instructions
        if str(p['id']) == str(panel_id):
            p['prompt'] = prompt
            p['scene_description'] = scene_description
            p['balloons'] = balloons
            p['status'] = 'editing' # Trigger regeneration
            
            # Context engineering overrides
            p['panel_style'] = kwargs.get('panel_style', p.get('panel_style'))
            p['instructions'] = kwargs.get('instructions', p.get('instructions'))
            
            # Use provided current_image_url for I2I. If None, the user unchecked I2I — do NOT fallback.
            p['current_image_url'] = kwargs.get('current_image_url')
            
            p['reference_image_url'] = kwargs.get('reference_image_url', p.get('reference_image_url'))
        
        # Ensure characters field exists (mapping from character_refs if necessary)
        if 'characters' not in p:
            p['characters'] = p.get('character_refs', [])
        
        # Fallback: if characters is still empty, extract from balloons
        if not p['characters']:
            balloon_chars = list(set(
                b.get('character') for b in p.get('balloons', []) 
                if b.get('character')
            ))
            if balloon_chars:
                p['characters'] = balloon_chars
                print(f"DEBUG: Inferred characters from balloons for panel {p.get('id')}: {balloon_chars}")
            
        processed_panels.append(p)

    state = {
        "action": "regenerate_panel",
        "project_id": project_id,
        "panel_id": panel_id,
        "world_model_summary": world_model_summary,
        "panels": processed_panels,
        "merged_pages": [],
        "style_guide": global_context.get('style_guide', ""),
        "current_image_url": kwargs.get('current_image_url'),
        "reference_image_url": kwargs.get('reference_image_url'),
        "global_context": global_context
    }
    
    try:
        # LangSmith tracing for direct graph call
        from langsmith import traceable
        from core.graph import create_comic_graph
        
        @traceable(name="regenerate_panel_flow", project_name=os.getenv("LANGCHAIN_PROJECT", "comic-draft-ai"))
        def run_traced():
            app = create_comic_graph()
            # Iniciar el grafo. El router interno llevará directamente a 'generator'
            return app.invoke(state, config={"recursion_limit": 5})
            
        updated_state = run_traced()
        # Notify backend via SQS
        notify_completion(project_id, updated_state, "regenerate_panel")
        return updated_state
    except Exception as e:
        notify_completion(project_id, {"error": str(e)}, "regenerate_panel")
        return {"error": str(e)}

def regenerate_merge_logic(project_id, instructions, **kwargs):
    """
    Logic for page merging with provided context.
    """
    print(f"--- REGENERATING MERGE: Project {project_id} ---")
    
    all_panels = kwargs.get('panels', [])
    world_model_summary = kwargs.get('world_model_summary', instructions if instructions else "Professional comic book style.")
    global_context = kwargs.get('global_context', {})
    
    # Pre-process panels
    processed_panels = []
    for p in all_panels:
        if 'characters' not in p:
            p['characters'] = p.get('character_refs', [])
        processed_panels.append(p)
        
    state = {
        "action": "regenerate_merge", # Note: Need to add this to router if needed later
        "project_id": project_id,
        "world_model_summary": world_model_summary,
        "panels": processed_panels,
        "merged_pages": [],
        "style_guide": global_context.get('style_guide', ""),
        "global_context": global_context
    }
    
    try:
        # LangSmith tracing for direct graph call
        from langsmith import traceable
        from core.graph import create_comic_graph
        
        @traceable(name="regenerate_merge_flow", project_name=os.getenv("LANGCHAIN_PROJECT", "comic-draft-ai"))
        def run_traced():
            app = create_comic_graph()
            # For merge, we might want to start further in the graph or just run full if not optimized
            # But the current merger node expects the full state.
            return app.invoke(state, config={"recursion_limit": 10})
            
        updated_state = run_traced()
        # Notify backend via SQS
        notify_completion(project_id, updated_state, "regenerate_merge")
        return updated_state
    except Exception as e:
        notify_completion(project_id, {"error": str(e)}, "regenerate_merge")
        return {"error": str(e)}

@app.entrypoint
def agent_invocation(payload, context):
    """
    Unified Bedrock Agent Entrypoint.
    Handles 'generate', 'regenerate_panel', and 'regenerate_merge'.
    """
    print(f"--- BEDROCK AGENT INVOCATION ---")
    print(f"Payload: {payload}")
    action = payload.get("action", "generate")
    project_id = payload.get("project_id")
    
    if not project_id:
        return {"status": "error", "message": "Missing project_id in payload"}
    
    if not action:
        return {"status": "error", "message": "Missing action in payload"}

    try:
        if action == "generate":
            result = generate_comic_logic(**payload)
        elif action == "regenerate_panel":
            result = regenerate_panel_logic(**payload)
        elif action == "regenerate_merge":
            result = regenerate_merge_logic(**payload)
        else:
            return {"status": "error", "message": f"Unknown action: {action}"}

        return {
            "status": "success",
            "action": action,
            "project_id": project_id,
            "result": result
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    print("--- STARTING UNIFIED BEDROCK AGENT CORE RUNTIME ---")
    app.run()
