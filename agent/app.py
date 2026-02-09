from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from core.graph import create_comic_graph
import os

load_dotenv(override=True)

app = Flask(__name__)
CORS(app)


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
    plan_only = data.get("plan_only", False)
    panels = data.get("panels", [])

    from worker import generate_comic_async
    # Disparar tarea asíncrona en Celery
    task = generate_comic_async.delay(
        project_id, 
        sources, 
        max_pages, 
        max_panels, 
        layout_style,
        plan_only=plan_only,
        panels=panels
    )

    return jsonify({
        "project_id": project_id,
        "task_id": task.id,
        "status": "queued",
        "message": "Generation process started in background"
    }), 202

@app.route('/regenerate-panel', methods=['POST'])
def regenerate_panel():
    data = request.json
    project_id = data.get("project_id")
    panel_id = data.get("panel_id")
    
    from worker import regenerate_panel_async
    task = regenerate_panel_async.delay(
        project_id, 
        panel_id,
        data.get("prompt"),
        data.get("scene_description"),
        data.get("balloons")
    )
    
    return jsonify({"project_id": project_id, "task_id": task.id, "status": "queued"}), 202

@app.route('/regenerate-merge', methods=['POST'])
def regenerate_merge():
    data = request.json
    project_id = data.get("project_id")
    instructions = data.get("instructions", "")
    
    from worker import regenerate_merge_async
    task = regenerate_merge_async.delay(project_id, instructions)
    
    return jsonify({"project_id": project_id, "task_id": task.id, "status": "queued"}), 202

if __name__ == '__main__':
    port = int(os.getenv("PORT", 8001))
    app.run(host='0.0.0.0', port=port, debug=os.getenv("DEBUG", "False") == "True")
