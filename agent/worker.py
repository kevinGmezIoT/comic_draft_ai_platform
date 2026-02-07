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
def generate_comic_async(project_id, sources, max_pages=3, max_panels=None, layout_style="dynamic"):
    print(f"Propagating task for project: {project_id}")
    
    initial_state = {
        "project_id": project_id,
        "sources": sources,
        "max_pages": max_pages,
        "max_panels": max_panels,
        "layout_style": layout_style,
        "panels": [],
        "merged_pages": [],
        "world_model_summary": "",
        "script_outline": [],
        "current_step": "start"
    }

    # Ejecutar el grafo de LangGraph
    backend_url = os.getenv('BACKEND_INTERNAL_URL', 'http://localhost:8000')
    webhook_url = f"{backend_url}/api/projects/{project_id}/callback/"

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
