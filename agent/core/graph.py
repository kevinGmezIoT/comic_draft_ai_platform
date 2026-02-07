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
    max_panels_per_page: int
    layout_style: str # "dynamic" | "vertical" | "grid"
    world_model_summary: str
    full_script: str
    script_outline: List[str]
    panels: List[Panel]
    merged_pages: List[dict] # [{page_number: 1, image_url: "..."}]
    plan_only: bool = False
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
    existing_panels = state.get("panels", [])
    max_panels = state.get("max_panels")
    
    # Solo salteamos si ya hay paneles Y no hay una contradicción con max_panels
    # Si max_panels está definido y es diferente al actual, debemos RE-PLANEAR
    if existing_panels and len(existing_panels) > 0:
        if not max_panels or len(existing_panels) == max_panels:
            print("--- SKIPPING STRATEGIC PLANNING (Existing layout fulfills count) ---")
            return {"current_step": "layout_designer"}
        else:
            print(f"--- RE-PLANNING: Current count {len(existing_panels)} vs Target {max_panels} ---")

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
    REGLAS ESTRICTAS DE LAYOUT:
    - MÁXIMO ABSOLUTO DE {state.get('max_pages', 3)} PÁGINAS. No te pases de este número.
    - MÁXIMO DE {state.get('max_panels_per_page', 4)} PANELES POR PÁGINA.
    - CANTIDAD TOTAL DE PANELES REQUERIDA: {state.get('max_panels') if state.get('max_panels') else 'Tu decisión experta'}.
    - IMPORTANTE: Si 'CANTIDAD TOTAL DE PANELES' está definida (es un número), DEBES generar EXACTAMENTE ese número de paneles, repartidos en las páginas indicadas.
    
    ESTILO NARRATIVO:
    - EVITA EL GRID RÍGIDO: Sugiere composiciones dinámicas (paneles que se solapan, ángulos cinematográficos).
    - COMPOSICIONES: Si el usuario pide algo específico como "enfrentados", refléjalo en el prompt y la descripción.
    
    Para cada panel, proporciona:
    - id: un identificador único (ej: p1_1)
    - page_number: número de página (máximo {state.get('max_pages', 3)})
    - order_in_page: orden del panel en la página
    - scene_description: descripción detallada de la acción
    - characters: lista de nombres de personajes presentes.
    - prompt: un prompt visual rico para generación de imagen.
    
    Responde ÚNICAMENTE con un JSON válido (lista de objetos).
    """
    
    try:
        # Fallback si no hay script ni guión (Prototipo/S3 simulado)
        if not state.get('full_script') or len(state['full_script'].strip()) < 10:
            print("--- WARNING: Script empty or too short. Using Template Fallback. ---")
            target_count = state.get('max_panels', 4) or 4
            panels = []
            for i in range(target_count):
                panels.append({
                    "id": f"p_temp_{i+1}",
                    "page_number": 1,
                    "order_in_page": i + 1,
                    "scene_description": f"Escena {i+1} (Plantilla)",
                    "characters": [],
                    "prompt": "Cinematic comic panel placeholder"
                })
        else:
            response = llm.invoke([
                SystemMessage(content="Eres un director de arte de cómics experto en descomposición de guiones. Responde SIEMPRE con un JSON válido."),
                HumanMessage(content=prompt)
            ])
            
            content = response.content.strip()
            print(f"DEBUG: LLM Planner Output: {content[:200]}...")

            if content.startswith("```json"):
                content = content[7:-3].strip()
            
            data = json.loads(content)
            # Manejar tanto lista [...] como objeto {"panels": [...]}
            if isinstance(data, dict):
                panels = data.get("panels", [])
            else:
                panels = data
        
        if not panels:
             raise ValueError("No panels were generated by the LLM or Fallback")

        # Inicializar campos faltantes
        for i, p in enumerate(panels):
            p.setdefault("id", f"p_{i}")
            p.setdefault("image_url", "")
            p.setdefault("status", "pending")
            
        return {"panels": panels, "current_step": "layout_designer"}
    except Exception as e:
        print(f"Error en planner: {e}")
        # Segundo nivel de fallback: Generar paneles mínimos forzados
        target_count = state.get('max_panels') or state.get('max_pages', 1) * 2
        fallback_panels = [{
            "id": f"f_{i}",
            "page_number": (i // state.get('max_panels_per_page', 4)) + 1,
            "order_in_page": i + 1,
            "scene_description": "Escena generada por recuperación de error.",
            "characters": [],
            "prompt": "Comic panel placeholder",
            "image_url": "",
            "status": "pending"
        } for i in range(target_count)]
        return {"panels": fallback_panels, "current_step": "layout_designer"}

def image_generator(state: AgentState):
    print("--- CONSISTENT IMAGE GENERATION ---")
    adapter = get_image_adapter()
    cm = CharacterManager(state["project_id"])
    
    updated_panels = []
    # Aseguramos el orden para que la generación (si es secuencial/streaming)    # Ordenar por página y orden de forma defensiva
    sorted_panels = sorted(state["panels"], key=lambda x: (x.get('page_number', 1), x.get('order_in_page', 0)))
    
    for panel in sorted_panels:
        # Lógica de salto refinada: 
        # Si tiene imagen y NO está pendiente de regenerar o editar, saltar.
        # Esto ignora panels con status 'completed' (del backend) o 'generated'.
        if panel.get("image_url") and panel.get("status") not in ["pending", "editing"]:
            updated_panels.append(panel)
            continue

        # Construir prompt robusto con consistencia
        char_prompts = [cm.get_character_prompt_segment(c) for c in panel.get("characters", [])]
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
    
    # Si los paneles ya tienen un layout definido (ej: por edición manual previa), respetarlo
    if any(p.get("layout") and p["layout"].get("w") for p in panels):
        print("--- SKIPPING LAYOUT DESIGN (Layout already defined) ---")
        return {"panels": panels, "current_step": "generator"}

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
                    # Si es confrontación (o simplemente 2), pondremos uno a cada lado
                    prompt_lower = str(p.get("prompt", "")).lower()
                    if "enfrentados" in prompt_lower or "confrontation" in prompt_lower or "face-off" in prompt_lower:
                        if i == 0:
                            p["layout"] = {"x": 5, "y": 10, "w": 42, "h": 80} # Izquierda (cinemático)
                        else:
                            p["layout"] = {"x": 53, "y": 10, "w": 42, "h": 80} # Derecha
                    elif "vertical split" in prompt_lower:
                        p["layout"] = {"x": i*50, "y": 0, "w": 50, "h": 100}
                    else:
                        p["layout"] = {"x": 0, "y": i*50, "w": 100, "h": 50}
                elif count == 3:
                    if i == 0:
                        p["layout"] = {"x": 0, "y": 0, "w": 100, "h": 40}
                    else:
                        p["layout"] = {"x": (i-1)*50, "y": 40, "w": 50, "h": 60}
                elif count == 4:
                     # Cuadrícula 2x2 elegante
                     p["layout"] = {"x": (i%2)*50, "y": (i//2)*50, "w": 50, "h": 50}
                else: # 5 o más
                    row = i // 2
                    col = i % 2
                    h = 100 / ( (count + 1) // 2 )
                    p["layout"] = {"x": col*50, "y": row*h, "w": 50, "h": h}
            
            updated_panels.append(p)

    return {"panels": updated_panels, "current_step": "generator"}

def page_merger(state: AgentState):
    print("--- ORGANIC PAGE MERGE (Image-to-Image with Composite & Balloons) ---")
    from core.utils import PageRenderer
    import os
    import requests
    from io import BytesIO
    from PIL import Image
    import tempfile
    
    adapter = get_image_adapter()
    renderer = PageRenderer()
    
    pages = {}
    for p in state["panels"]:
        p_num = p["page_number"]
        if p_num not in pages: pages[p_num] = []
        pages[p_num].append(p)
        
    merged_results = []
    
    for page_num, panel_list in pages.items():
        print(f"Merging Page {page_num}...")
        
        # 1. Crear el collage base con globos (como guía para la IA)
        composite_path = renderer.create_composite_page(panel_list, include_balloons=True)
        
        panel_descriptions = " | ".join([p["scene_description"] for p in panel_list])
        merge_prompt = f"ORGANIC COMIC PAGE MERGE. Task: Synthesize these scenes and speech bubbles into a single, cohesive comic page. Blend the backgrounds smoothly. Keep the placements of characters and balloons. Style: {state.get('world_model_summary', '')}. Professional comic art style."
        
        try:
            # 2. Generar mezcla orgánica via Image-to-Image
            raw_merged_url = adapter.generate_image(merge_prompt, quality="hd", init_image_path=composite_path) 
            
            # 3. Aplicar "Overlays" nítidos sobre el resultado de la IA
            # (Descargamos el resultado de la IA para ponerle texto legible encima)
            response = requests.get(raw_merged_url, timeout=15)
            with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_raw:
                tmp_raw.write(response.content)
                tmp_raw_path = tmp_raw.name
                
            final_composite_path = renderer.apply_final_overlays(tmp_raw_path, panel_list)
            
            # Nota: En producción esto se subiría a S3. 
            # Para el prototipo, devolvemos la URL de la IA (raw) por ahora 
            # o simulamos que la final es la procesada (si el adapter manejara subida).
            # Como el backend espera una URL, mantendremos raw_merged_url o coordinaremos.
            # Sin embargo, para que el usuario vea el resultado con globos nítidos,
            # lo ideal es que el Agente devuelva una URL accesible.
            
            merged_results.append({"page_number": page_num, "image_url": raw_merged_url})
            print(f"DEBUG: Final sharp balloons ready at {final_composite_path} (local)")
            
        finally:
            if os.path.exists(composite_path): os.remove(composite_path)
            # if os.path.exists(tmp_raw_path): os.remove(tmp_raw_path)
        
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
    workflow.add_edge("world_model_builder", "planner")
    workflow.add_edge("planner", "layout_designer")

    # Camino condicional según plan_only
    def should_continue(state: AgentState):
        if state.get("plan_only"):
            return "end"
        return "continue"

    workflow.add_conditional_edges(
        "layout_designer",
        should_continue,
        {
            "end": END,
            "continue": "generator"
        }
    )

    workflow.add_edge("generator", "balloons")
    workflow.add_edge("balloons", "merger")
    workflow.add_edge("merger", END)

    return workflow.compile()
