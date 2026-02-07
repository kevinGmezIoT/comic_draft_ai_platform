from typing import TypedDict, List, Annotated
from langgraph.graph import StateGraph, END
from .adapters import get_image_adapter
from .knowledge import KnowledgeManager, CharacterManager
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
import json
import os

class Panel(TypedDict):
    id: str
    page_number: int
    order_in_page: int
    prompt: str
    scene_description: str
    characters: List[str]
    image_url: str
    status: str
    balloons: List[dict] = []

class AgentState(TypedDict):
    project_id: str
    sources: List[str]
    max_pages: int
    max_panels: int
    layout_style: str # "dynamic" | "vertical" | "grid"
    world_model_summary: str
    full_script: str
    script_outline: List[str]
    panels: List[Panel]
    merged_pages: List[dict] # [{page_number: 1, image_url: "..."}]
    current_step: str

def ingest_and_rag(state: AgentState):
    print("--- RAG & INGESTION ---")
    km = KnowledgeManager(state["project_id"])
    km.ingest_from_urls(state["sources"])
    
    # Extraer el resumen del mundo
    world_info = km.query_world_rules("Describe el estilo artístico, personajes principales y escenarios.")
    summary = "\n".join([doc.page_content for doc in world_info])
    
    # Extraer específicamente el guión/trama
    script_info = km.query_world_rules("Extrae el guión completo o la trama detallada de la historia.")
    full_script = "\n".join([doc.page_content for doc in script_info])
    
    return {
        "current_step": "world_model_builder", 
        "world_model_summary": summary,
        "full_script": full_script
    }

def world_model_builder(state: AgentState):
    print("--- WORLD MODEL BUILDING (Characters & Scenarios) ---")
    cm = CharacterManager(state["project_id"])
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    
    prompt = f"""
    Basándote en este resumen del mundo, identifica a los personajes principales.
    Para cada personaje, extrae su nombre y una descripción física detallada para generación de imágenes.
    
    RESUMEN:
    {state['world_model_summary']}
    
    Responde en formato JSON:
    {{"characters": [{{"name": "...", "description": "..."}}]}}
    """
    
    try:
        response = llm.invoke(prompt)
        content = response.content.strip()
        if content.startswith("```json"):
            content = content[7:-3].strip()
        data = json.loads(content)
        
        for char in data.get("characters", []):
            cm.register_character(char["name"], char["description"], [])
            print(f"Registered character: {char['name']}")
    except Exception as e:
        print(f"Error extracting characters: {e}")
        
    return {"current_step": "planner"}

def planner(state: AgentState):
    print("--- STRATEGIC PLANNING ---")
    # Usar un modelo capaz de razonar el layout
    llm = ChatOpenAI(model="gpt-4o", temperature=0.2)
    
    prompt = f"""
    Basándote en el siguiente SUMMARY del mundo y SCRIPT:
    
    SUMMARY:
    {state['world_model_summary']}
    
    SCRIPT:
    {state['full_script']}
    
    Divide la historia en una lista de paneles para un cómic. 
    REGLAS DE LAYOUT Y CREATIVIDAD:
    - MÁXIMO DE {state.get('max_pages', 3)} PÁGINAS.
    - CANTIDAD TOTAL DE PANELES REQUERIDA: {state.get('max_panels') if state.get('max_panels') else 'Tu decisión experta'}.
    - EVITA EL GRID RÍGIDO: Sugiere composiciones dinámicas (paneles que se solapan, ángulos cinematográficos, espacios negativos).
    - FLUJO NARRATIVO: Cada panel debe tener un propósito visual claro.
    
    Si 'CANTIDAD TOTAL DE PANELES' está definida, DEBES ajustarte exactamente a ese número.
    
    Para cada panel, proporciona:
    - id: un identificador único (ej: p1_1)
    - page_number: número de página (máximo {state.get('max_pages', 3)})
    - order_in_page: orden del panel en la página
    - scene_description: descripción detallada de la acción
    - characters: lista de nombres de personajes presentes (exactamente como se llaman en el summary)
    - prompt: un prompt visual rico para generación de imagen (DALL-E 3 style), insistiendo en el ángulo de cámara y la iluminación.
    
    Responde ÚNICAMENTE con un JSON válido (lista de objetos).
    """
    
    try:
        response = llm.invoke([
            SystemMessage(content="Eres un director de arte de cómics experto en descomposición de guiones."),
            HumanMessage(content=prompt)
        ])
        
        content = response.content.strip()
        if content.startswith("```json"):
            content = content[7:-3].strip()
        
        panels = json.loads(content)
        
        # Inicializar campos faltantes
        for p in panels:
            p.setdefault("image_url", "")
            p.setdefault("status", "pending")
            
        return {"panels": panels, "current_step": "layout_designer"}
    except Exception as e:
        print(f"Error en planner: {e}")
        # Fallback a un panel de error o vacío
        return {"panels": [], "current_step": "error"}

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
        
    return {"panels": updated_panels, "current_step": "balloons"}

def layout_designer(state: AgentState):
    print("--- DEFINING PAGE LAYOUTS (Templates) ---")
    panels = state["panels"]
    # Agrupar por página
    pages = {}
    for p in panels:
        p_num = p["page_number"]
        if p_num not in pages: pages[p_num] = []
        pages[p_num].append(p)
    
    updated_panels = []
    
    layout_pref = state.get("layout_style", "dynamic")
    
    # Definiciones de templates básicos (coordenadas relativas en una hoja de 800x1200 aprox)
    for page_num, p_list in pages.items():
        count = len(p_list)
        p_list = sorted(p_list, key=lambda x: x["order_in_page"])
        
        for i, p in enumerate(p_list):
            if layout_pref == "vertical":
                # Fuerza stack vertical
                h_per_panel = 100 / count
                p["layout"] = {"x": 0, "y": i*h_per_panel, "w": 100, "h": h_per_panel}
            elif layout_pref == "grid" and count >= 4:
                # Fuerza grid 2x2 si hay 4+
                row = i // 2
                col = i % 2
                p["layout"] = {"x": col*50, "y": row*50, "w": 50, "h": 50}
            else:
                # "dynamic" o fallback: Lógica según cantidad
                if count == 1:
                    p["layout"] = {"x": 0, "y": 0, "w": 100, "h": 100}
                elif count == 2:
                    p["layout"] = {"x": 0, "y": i*50, "w": 100, "h": 50}
                elif count == 3:
                    if i == 0:
                        p["layout"] = {"x": 0, "y": 0, "w": 100, "h": 50}
                    else:
                        p["layout"] = {"x": (i-1)*50, "y": 50, "w": 50, "h": 50}
                else: # 4 o más
                    row = i // 2
                    col = i % 2
                    p["layout"] = {"x": col*50, "y": row*50, "w": 50, "h": 50}
            
            updated_panels.append(p)

    return {"panels": updated_panels, "current_step": "generator"}

def page_merger(state: AgentState):
    print("--- ORGANIC PAGE MERGE (Image-to-Image) ---")
    adapter = get_image_adapter()
    
    # Agrupar paneles por página
    pages = {}
    for p in state["panels"]:
        p_num = p["page_number"]
        if p_num not in pages: pages[p_num] = []
        pages[p_num].append(p)
        
    merged_results = []
    
    for page_num, panel_list in pages.items():
        print(f"Merging Page {page_num}...")
        # En una implementación real, aquí se crearía un collage de los panels
        # y se pasaría como init_image al adaptador.
        # Por ahora, simulamos el prompt de condensación orgánica.
        panel_descriptions = " | ".join([p["scene_description"] for p in panel_list])
        merge_prompt = f"Comic book page layout, organic ink and painting merge of the following scenes: {panel_descriptions}. Estilo: {state['world_model_summary'][:200]}. Cinematic composition, professional comic layout."
        
        # Simulación de Image-to-Image / Organic Condensation
        panel_refs = ", ".join([f"[Panel {p['id']}: {p['image_url']}]" for p in panel_list if p["image_url"]])
        merge_prompt = f"ORGANIC COMIC PAGE MERGE. Reference Images: {panel_refs}. Task: Synthesize these scenes into a single, cohesive comic page. Blend the backgrounds and characters smoothly. Use overlapping panels and hand-drawn borders. Style: {state['world_model_summary'][:200]}. Cinematic layout, professional comic art."
        
        merged_url = adapter.generate_image(merge_prompt, quality="hd") 
        merged_results.append({"page_number": page_num, "image_url": merged_url})
        
    return {"merged_pages": merged_results, "current_step": "done"}

def balloon_generator(state: AgentState):
    print("--- GENERATING DIALOGUE BALLOONS ---")
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    
    # Preparamos los paneles para que el LLM les asigne texto
    panels_context = []
    for p in state["panels"]:
        panels_context.append({
            "id": p["id"],
            "scene_description": p["scene_description"],
            "characters": p["characters"]
        })
        
    prompt = f"""
    Basándote en el GUION y la descripción de los PANELES, genera los diálogos y cajas de narración.
    
    GUION:
    {state['full_script']}
    
    PANELES:
    {json.dumps(panels_context, indent=2)}
    
    Para cada panel, devuelve una lista de globos con:
    - type: "dialogue" | "narration"
    - character: nombre del personaje (o null si es narración)
    - text: el contenido del texto
    - position_hint: "top-left" | "top-right" | "bottom-center" (donde crees que queda mejor)
    
    Responde en JSON:
    {{"panels": [{{"id": "...", "balloons": [...]}}]}}
    """
    
    try:
        response = llm.invoke(prompt)
        content = response.content.strip()
        if content.startswith("```json"):
            content = content[7:-3].strip()
        data = json.loads(content)
        
        # Mapear balloons de vuelta a los paneles
        balloons_map = {p["id"]: p["balloons"] for p in data.get("panels", [])}
        
        updated_panels = []
        for p in state["panels"]:
            p["balloons"] = balloons_map.get(p["id"], [])
            updated_panels.append(p)
            
        return {"panels": updated_panels, "current_step": "merger"}
    except Exception as e:
        print(f"Error generating balloons: {e}")
        return {"current_step": "error"}

def create_comic_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("ingest", ingest_and_rag)
    workflow.add_node("world_model_builder", world_model_builder)
    workflow.add_node("planner", planner)
    workflow.add_node("layout_designer", layout_designer)
    workflow.add_node("generator", image_generator)
    workflow.add_node("balloons", balloon_generator)
    workflow.add_node("merger", page_merger)

    workflow.set_entry_point("ingest")
    workflow.add_edge("ingest", "world_model_builder")
    workflow.add_edge("world_model_builder", "planner")
    workflow.add_edge("planner", "layout_designer")
    workflow.add_edge("layout_designer", "generator")
    workflow.add_edge("generator", "balloons")
    workflow.add_edge("balloons", "merger")
    workflow.add_edge("merger", END)

    return workflow.compile()
