from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from core.graph import create_comic_graph
import os

load_dotenv(override=True)

app = Flask(__name__)
CORS(app)

from worker import generate_comic_async

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "service": "comic-agent"})

@app.route('/generate', methods=['POST'])
def generate_comic():
    data = request.json
    project_id = data.get("project_id")
    sources = data.get("sources", [])
    max_pages = data.get("max_pages", 3)
    max_panels = data.get("max_panels")
    layout_style = data.get("layout_style", "dynamic")

    # Disparar tarea asíncrona en Celery
    task = generate_comic_async.delay(project_id, sources, max_pages, max_panels, layout_style)

    return jsonify({
        "project_id": project_id,
        "task_id": task.id,
        "status": "queued",
        "message": "Generation process started in background"
    }), 202

@app.route('/edit-panel', methods=['POST'])
def edit_panel():
    # Lógica simplificada para editar un panel específico
    data = request.json
    # Implementar llamada al adaptador.edit_image()
    return jsonify({"status": "processing", "message": "Inpainting not yet implemented in prototype"})

if __name__ == '__main__':
    port = int(os.getenv("PORT", 8001))
    app.run(host='0.0.0.0', port=port, debug=os.getenv("DEBUG", "False") == "True")
