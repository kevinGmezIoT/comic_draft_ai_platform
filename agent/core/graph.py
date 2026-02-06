from typing import TypedDict, List, Annotated
from langgraph.graph import StateGraph, END
from .adapters import get_image_adapter
from .knowledge import KnowledgeManager, CharacterManager

class Panel(TypedDict):
    id: str
    page_number: int
    order_in_page: int
    prompt: str
    scene_description: str
    characters: List[str]
    image_url: str
    status: str

class AgentState(TypedDict):
    project_id: str
    sources: List[str]
    world_model_summary: str
    script_outline: List[str]
    panels: List[Panel]
    current_step: str

def ingest_and_rag(state: AgentState):
    print("--- RAG & INGESTION ---")
    km = KnowledgeManager(state["project_id"])
    # Procesar archivos de S3
    km.ingest_from_urls(state["sources"])
    
    # Extraer el resumen del mundo (World Model)
    world_info = km.query_world_rules("Describe el estilo artístico, personajes principales y escenarios.")
    summary = "\n".join([doc.page_content for doc in world_info])
    
    return {"current_step": "planner", "world_model_summary": summary}

def planner(state: AgentState):
    print("--- STRATEGIC PLANNING ---")
    # En una implementación real, aquí se usaría un LLM para dividir el guión
    # Asegurando el orden correcto (Page 1 -> Panel 1, 2, 3...)
    panels = [
        {
            "id": "p1_1", 
            "page_number": 1, "order_in_page": 1,
            "scene_description": "Héroe llegando a la ciudad",
            "characters": ["Héroe"],
            "prompt": "Fondo de ciudad futurista, plano medio del Héroe", 
            "image_url": "", "status": "pending"
        },
        {
            "id": "p1_2", 
            "page_number": 1, "order_in_page": 2,
            "scene_description": "Primer plano del villano",
            "characters": ["Villano"],
            "prompt": "Villano sonriendo malvadamente, sombras dramáticas", 
            "image_url": "", "status": "pending"
        }
    ]
    return {"panels": panels, "current_step": "generator"}

def image_generator(state: AgentState):
    print("--- CONSISTENT IMAGE GENERATION ---")
    adapter = get_image_adapter()
    cm = CharacterManager(state["project_id"])
    
    updated_panels = []
    # Aseguramos el orden para que la generación (si es secuencial/streaming) tenga sentido
    sorted_panels = sorted(state["panels"], key=lambda x: (x['page_number'], x['order_in_page']))
    
    for panel in sorted_panels:
        # Construir prompt robusto con consistencia
        char_prompts = [cm.get_character_prompt_segment(c) for c in panel["characters"]]
        full_prompt = f"{panel['prompt']}. Estilo: {state['world_model_summary'][:200]}. " + " ".join(char_prompts)
        
        # Image-to-image si ya existe una versión previa (v2, edit)
        if panel.get("image_url") and panel["status"] == "editing":
            url = adapter.edit_image(panel["image_url"], full_prompt)
        else:
            url = adapter.generate_image(full_prompt)
            
        panel["image_url"] = url
        panel["status"] = "generated"
        updated_panels.append(panel)
        
    return {"panels": updated_panels, "current_step": "done"}

def create_comic_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("ingest", ingest_and_rag)
    workflow.add_node("planner", planner)
    workflow.add_node("generator", image_generator)

    workflow.set_entry_point("ingest")
    workflow.add_edge("ingest", "planner")
    workflow.add_edge("planner", "generator")
    workflow.add_edge("generator", END)

    return workflow.compile()

    workflow.set_entry_point("ingest")
    workflow.add_edge("ingest", "planner")
    workflow.add_edge("planner", "generator")
    workflow.add_edge("generator", END)

    return workflow.compile()
