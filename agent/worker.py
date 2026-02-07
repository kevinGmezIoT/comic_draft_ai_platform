import os
from celery import Celery
from core.graph import create_comic_graph
from dotenv import load_dotenv
import requests

load_dotenv(override=True)

# Configuración de Celery con Redis
celery_app = Celery(
    'comic_tasks',
    broker=os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
    backend=os.getenv('REDIS_URL', 'redis://localhost:6379/0')
)

graph = create_comic_graph()

@celery_app.task(name='generate_comic_async')
def generate_comic_async(project_id, sources, max_pages=3, max_panels=None, layout_style="dynamic", **kwargs):
    print(f"Propagating task for project: {project_id}")
    
    initial_state = {
        "project_id": project_id,
        "sources": sources,
        "max_pages": max_pages,
        "max_panels": max_panels,
        "max_panels_per_page": kwargs.get("max_panels_per_page", 4),
        "layout_style": layout_style,
        "plan_only": kwargs.get("plan_only", False),
        "panels": kwargs.get("panels", []),
        "merged_pages": [],
        "world_model_summary": "",
        "script_outline": [],
        "current_step": "start"
    }

    # Ejecutar el grafo de LangGraph
    backend_url = os.getenv('BACKEND_INTERNAL_URL', 'http://localhost:8000')
    webhook_url = f"{backend_url}/api/projects/{project_id}/callback/"

    # Import local para evitar posibles problemas de importación circular indirectos
    # though here it's fine as it's at the top level in the task, but wait, 
    # tasks are pickled by celery, let's keep it simple.

    try:
        result = graph.invoke(initial_state)
        # Notificar éxito
        requests.post(webhook_url, json={
            "status": "completed",
            "result": result
        })
        print(f"Successfully notified backend for project {project_id}")
        return result
    except Exception as e:
        error_msg = str(e)
        print(f"Error in graph execution for project {project_id}: {error_msg}")
        
        # Notificar fallo al backend
        try:
            requests.post(webhook_url, json={
                "status": "failed",
                "error": error_msg
            })
        except Exception as webhook_err:
            print(f"Failed to notify backend about the failure: {webhook_err}")
            
        return {"current_step": "error", "error": error_msg}

@celery_app.task(name='regenerate_panel_async')
def regenerate_panel_async(project_id, panel_id, prompt, scene_description, balloons):
    print(f"Regenerating panel {panel_id} for project: {project_id}")
    from core.graph import image_generator
    
    # Obtener el estado completo actual del proyecto desde el backend
    backend_url = os.getenv('BACKEND_INTERNAL_URL', 'http://localhost:8000')
    response = requests.get(f"{backend_url}/api/projects/{project_id}/")
    project_data = response.json()
    
    all_panels = []
    for page in project_data.get('pages', []):
        for p in page.get('panels', []):
            # Normalización de campos del backend al agente
            p['order_in_page'] = p.get('order', 0)
            p['characters'] = p.get('character_refs', [])
            
            if p['id'] == panel_id:
                # Marcar este panel como pendiente de regeneración con los nuevos datos
                p['prompt'] = prompt
                p['scene_description'] = scene_description
                p['balloons'] = balloons
                p['status'] = 'pending' 
            all_panels.append(p)

    state = {
        "project_id": project_id,
        "world_model_summary": project_data.get('world_model_summary', "Cyber Noir. Cinematic lighting."),
        "panels": all_panels,
        "merged_pages": [] # No regeneramos el merge aquí a menos que sea necesario
    }
    
    webhook_url = f"{backend_url}/api/projects/{project_id}/callback/"
    
    try:
        updated_state = image_generator(state)
        requests.post(webhook_url, json={
            "status": "completed",
            "result": updated_state
        })
        return updated_state
    except Exception as e:
        requests.post(webhook_url, json={"status": "failed", "error": str(e)})
        return {"error": str(e)}

@celery_app.task(name='regenerate_merge_async')
def regenerate_merge_async(project_id, instructions):
    print(f"Regenerating merge for project: {project_id} with instructions: {instructions}")
    from core.graph import page_merger
    
    backend_url = os.getenv('BACKEND_INTERNAL_URL', 'http://localhost:8000')
    response = requests.get(f"{backend_url}/api/projects/{project_id}/")
    project_data = response.json()
    
    all_panels = []
    for page in project_data.get('pages', []):
        for p in page.get('panels', []):
            # Normalización
            p['order_in_page'] = p.get('order', 0)
            p['characters'] = p.get('character_refs', [])
            all_panels.append(p)
        
    state = {
        "project_id": project_id,
        "world_model_summary": instructions if instructions else "Professional comic book style.",
        "panels": all_panels,
        "merged_pages": []
    }
    
    webhook_url = f"{backend_url}/api/projects/{project_id}/callback/"
    
    try:
        updated_state = page_merger(state)
        requests.post(webhook_url, json={
            "status": "completed",
            "result": updated_state
        })
        return updated_state
    except Exception as e:
        requests.post(webhook_url, json={"status": "failed", "error": str(e)})
        return {"error": str(e)}
