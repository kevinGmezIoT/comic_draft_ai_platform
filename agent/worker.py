import os
from celery import Celery
from core.graph import create_comic_graph
from dotenv import load_dotenv
import requests

load_dotenv()

# Configuración de Celery con Redis
celery_app = Celery(
    'comic_tasks',
    broker=os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
    backend=os.getenv('REDIS_URL', 'redis://localhost:6379/0')
)

graph = create_comic_graph()

@celery_app.task(name='generate_comic_async')
def generate_comic_async(project_id, sources):
    print(f"Propagating task for project: {project_id}")
    
    initial_state = {
        "project_id": project_id,
        "sources": sources,
        "panels": [],
        "world_model_summary": "",
        "script_outline": [],
        "current_step": "start"
    }

    # Ejecutar el grafo de LangGraph
    result = graph.invoke(initial_state)

    # Notificar al backend que el proceso ha terminado
    backend_url = os.getenv('BACKEND_INTERNAL_URL', 'http://localhost:8000')
    webhook_url = f"{backend_url}/api/projects/{project_id}/callback/"
    
    try:
        requests.post(webhook_url, json={
            "status": "completed",
            "result": result
        })
        print(f"Successfully notified backend for project {project_id}")
    except Exception as e:
        print(f"Failed to notify backend: {e}")

    return result
