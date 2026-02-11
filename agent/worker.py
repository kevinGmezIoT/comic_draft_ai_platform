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
        "reference_images": [],
        "global_context": kwargs.get("global_context", {})
    }

    try:
        result = graph.invoke(initial_state)
        
        # Notify backend via SQS
        if queue_url:
            print(f"DEBUG: Sending result to SQS Queue: {queue_url}")
            try:
                message_body = json.dumps({
                    "project_id": project_id,
                    "status": "completed",
                    "result": result
                })
                sqs.send_message(QueueUrl=queue_url, MessageBody=message_body)
                print("DEBUG: SQS message sent successfully.")
            except Exception as e:
                print(f"ERROR: Failed to send SQS message: {e}")
        else:
            print("WARNING: AWS_SQS_QUEUE_URL not set. Results will not be sent to backend.")
            
        return result
    except Exception as e:
        print(f"Error in graph execution: {e}")
        # Send failure notification if possible
        if queue_url:
            try:
                sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps({
                    "project_id": project_id,
                    "status": "failed",
                    "error": str(e)
                }))
            except: pass
        return {"current_step": "error", "error": str(e)}

def regenerate_panel_logic(project_id, panel_id, prompt, scene_description, balloons):
    """
    Logic for single panel regeneration.
    """
    print(f"--- REGENERATING PANEL: {panel_id} in Project {project_id} ---")
    from core.graph import image_generator
    
    backend_url = os.getenv('BACKEND_INTERNAL_URL', 'http://localhost:8000')
    response = requests.get(f"{backend_url}/api/projects/{project_id}/")
    project_data = response.json()
    
    all_panels = []
    for page in project_data.get('pages', []):
        for p in page.get('panels', []):
            p['order_in_page'] = p.get('order', 0)
            p['characters'] = p.get('character_refs', [])
            
            if p['id'] == panel_id:
                p['prompt'] = prompt
                p['scene_description'] = scene_description
                p['balloons'] = balloons
                p['status'] = 'pending' 
            all_panels.append(p)

    state = {
        "project_id": project_id,
        "world_model_summary": project_data.get('world_model_summary', ""),
        "panels": all_panels,
        "merged_pages": []
    }
    
    try:
        updated_state = image_generator(state)
        return updated_state
    except Exception as e:
        return {"error": str(e)}

def regenerate_merge_logic(project_id, instructions):
    """
    Logic for page merging.
    """
    print(f"--- REGENERATING MERGE: Project {project_id} ---")
    from core.graph import page_merger
    
    backend_url = os.getenv('BACKEND_INTERNAL_URL', 'http://localhost:8000')
    response = requests.get(f"{backend_url}/api/projects/{project_id}/")
    project_data = response.json()
    
    all_panels = []
    for page in project_data.get('pages', []):
        for p in page.get('panels', []):
            p['order_in_page'] = p.get('order', 0)
            p['characters'] = p.get('character_refs', [])
            all_panels.append(p)
        
    state = {
        "project_id": project_id,
        "world_model_summary": instructions if instructions else "Professional comic book style.",
        "panels": all_panels,
        "merged_pages": []
    }
    
    try:
        updated_state = page_merger(state)
        return updated_state
    except Exception as e:
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
        return {"status": "error", "message": "Missing project_id in payload 2"}

    try:
        if action == "generate":
            result = generate_comic_logic(
                project_id, 
                payload.get("sources", []),
                max_pages=payload.get("max_pages", 3),
                max_panels=payload.get("max_panels"),
                layout_style=payload.get("layout_style", "dynamic"),
                plan_only=payload.get("plan_only", False),
                panels=payload.get("panels", [])
            )
        elif action == "regenerate_panel":
            result = regenerate_panel_logic(
                project_id,
                payload.get("panel_id"),
                payload.get("prompt"),
                payload.get("scene_description"),
                payload.get("balloons", [])
            )
        elif action == "regenerate_merge":
            result = regenerate_merge_logic(
                project_id,
                payload.get("instructions")
            )
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
