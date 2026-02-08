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
    
    # Si ya tenemos paneles con IDs reales (UUIDs) y descripción, probablemente 
    # venimos de una edición manual o regeneración de arte selectiva.
    # En ese caso, SOLO planificamos si nos falta algún panel o si nos piden explícitamente re-planear (cambiando max_panels).
    if existing_panels and len(existing_panels) > 0:
        if not max_panels or len(existing_panels) == max_panels:
            # Verificar si tienen contenido real
            if any(p.get('scene_description') for p in existing_panels):
                print("--- SKIPPING STRATEGIC PLANNING (Using existing panels) ---")
                return {"panels": existing_panels, "current_step": "layout_designer"}

    print("--- STRATEGIC PLANNING ---")
    # Usar un modelo capaz de razonar el layout
    llm = ChatOpenAI(model="gpt-4o", temperature=0.2)
    
    prompt = f"""
    Basándote en el siguiente SUMMARY del mundo y SCRIPT:
    
    SUMMARY:
    {state['world_model_summary']}
    
    SCRIPT:
    {state['full_script']}
    
    TAMAÑO DE PÁGINA RECOMENDADO: {state.get('canvas_dimensions', '800x1100 (A4)')}
    ESTILO DE LAYOUT: {state.get('layout_style', 'dynamic')}

    Divide la historia en una lista de paneles para un cómic. 
    REGLAS ESTRICTAS DE LAYOUT:
    - MÁXIMO ABSOLUTO DE {state.get('max_pages', 3)} PÁGINAS.
    - MÁXIMO DE {state.get('max_panels_per_page', 4)} PANELES POR PÁGINA.
    - CANTIDAD TOTAL DE PANELES REQUERIDA: {state.get('max_panels') if state.get('max_panels') else 'Tu decisión experta'}.
    
    ESTILO NARRATIVO:
    - EVITA EL GRID RÍGIDO: Sugiere composiciones dinámicas (paneles que se solapan, ángulos cinematográficos).
    - Ten en cuenta el espacio para los globos de texto que se generarán después.
    
    Para cada panel, proporciona:
    - id: un identificador único (ej: p1_1)
    - page_number: número de página (máximo {state.get('max_pages', 3)})
    - order_in_page: orden del panel en la página
    - scene_description: descripción detallada de la acción (pensada para un modelo multimodal)
    - characters: lista de nombres de personajes presentes.
    - prompt: un prompt visual rico para generación de imagen.
    
    Responde ÚNICAMENTE con un JSON válido.
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

        for i, p in enumerate(panels):
            p.setdefault("id", f"p_{i}")
            p.setdefault("image_url", "")
            p.setdefault("status", "pending")
            p.setdefault("characters", [])
            
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
    print("--- MULTIMODAL IMAGE GENERATION ---")
    adapter = get_image_adapter()
    cm = CharacterManager(state["project_id"])
    llm = ChatOpenAI(model="gpt-4o", temperature=0.3)
    
    updated_panels = []
    # Ordenar por página y orden de forma defensiva
    sorted_panels = sorted(state["panels"], key=lambda x: (x.get('page_number', 1), x.get('order_in_page', 0)))
    
    for panel in sorted_panels:
        # Lógica de salto: Si tiene imagen y NO está pendiente de regenerar, saltar.
        if panel.get("image_url") and panel.get("status") not in ["pending", "editing"]:
            updated_panels.append(panel)
            continue

        # 1. Razonamiento Multimodal: GPT-4o para potenciar el prompt visual según el layout
        layout = panel.get("layout", {"w": 50, "h": 50})
        w, h = layout.get("w", 50), layout.get("h", 50)
        
        # Determinar aspect ratio para el modelo de imagen
        aspect_ratio = "1:1"
        if w / h > 1.2: aspect_ratio = "16:9"
        elif h / w > 1.2: aspect_ratio = "9:16"

        char_names = panel.get("characters", [])
        char_descriptions = [cm.get_character_prompt_segment(c) for c in char_names]
        
        reasoning_prompt = f"""
        Actúa como un Director de Fotografía de Cómics. 
        ESCENA: {panel['scene_description']}
        PERSONAJES: {", ".join(char_names)}
        CONTEXTO MUNDO: {state['world_model_summary'][:300]}
        DISEÑO PANEL: {w}% de ancho x {h}% de alto.
        
        Genera un PROMPT VISUAL altamente detallado para una IA generadora de imágenes. 
        Enfócate en la composición cinematográfica que mejor se adapte a un panel de estas dimensiones ({aspect_ratio}).
        Incluye detalles del estilo artístico de la obra, iluminación, ángulo de cámara y las descripciones de los personajes:
        {" ".join(char_descriptions)}
        
        Responde ÚNICAMENTE con el prompt final.
        """
        
        try:
            visual_reasoning = llm.invoke(reasoning_prompt).content.strip()
            print(f"Multimodal Insight for Panel {panel['id']}: {visual_reasoning[:50]}...")
        except:
            visual_reasoning = panel['prompt']

        # 2. Generación de Imagen con Aspect Ratio
        if panel.get("image_url") and panel["status"] == "editing":
            url = adapter.edit_image(panel["image_url"], visual_reasoning)
        else:
            url = adapter.generate_image(visual_reasoning, aspect_ratio=aspect_ratio)
            
        panel["image_url"] = url
        panel["status"] = "generated"
        updated_panels.append(panel)
        
    return {"panels": updated_panels, "current_step": "balloons"}

def layout_designer(state: AgentState):
    print("--- DEFINING PAGE LAYOUTS (Templates) ---")
    panels = state.get("panels", [])
    if not panels:
        print("--- WARNING: No panels to design layout for. ---")
        return {"current_step": "generator"}
    
    # Si los paneles ya tienen un layout definido con dimensiones reales, respetarlo
    # Solo diseñamos layout para los que les falte
    panels_needing_layout = [p for p in panels if not (p.get("layout") and p["layout"].get("w") and p["layout"].get("w") > 0)]
    
    if not panels_needing_layout:
        print("--- SKIPPING LAYOUT DESIGN (All panels have layout defined) ---")
        return {"panels": panels, "current_step": "generator"}

    # Si hay una mezcla, diseñamos solo para los que faltan (o re-calculamos si la página es nueva)
    # Por simplicidad en este prototipo, si faltan algunos, re-calculamos los de esas páginas.
    pages_to_redesign = set(p["page_number"] for p in panels_needing_layout)
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
            # NO TOCAR si ya tiene layout (ej: editado manualmente en el frontend)
            if p.get("layout") and p["layout"].get("w", 0) > 0:
                updated_panels.append(p)
                continue

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
        
        # 1.5. Análisis Multimodal para Blend (Opcional pero recomendado para alta calidad)
        # Podríamos usar GPT-4o con la imagen 'composite_path' para generar una descripción de mezcla.
        llm_vision = ChatOpenAI(model="gpt-4o", temperature=0.2)
        
        # Para enviar la imagen a GPT-4o, la codificamos en b64
        import base64
        with open(composite_path, "rb") as f:
            composite_b64 = base64.b64encode(f.read()).decode("utf-8")
        
        vision_prompt = "Esta es una maqueta de una página de cómic con paneles y globos. Describe cómo deberían mezclarse los fondos de manera artística y orgánica para que parezca una sola ilustración fluida, manteniendo la posición de los personajes y globos."
        
        try:
            message = HumanMessage(
                content=[
                    {"type": "text", "text": vision_prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{composite_b64}"},
                    },
                ]
            )
            vision_response = llm_vision.invoke([message])
            visual_blend_description = vision_response.content
            print(f"Visual Blend Insight: {visual_blend_description[:100]}...")
        except Exception as e:
            print(f"Vision analysis failed: {e}. Falling back to default prompt.")
            visual_blend_description = "Blend the backgrounds smoothly."

        merge_prompt = f"ORGANIC COMIC PAGE MERGE. Instrucciones visuales: {visual_blend_description}. Style: {state.get('world_model_summary', '')}. Professional comic art style."
        
        try:
            # 2. Generar mezcla orgánica via Image-to-Image
            raw_merged_s3_key = adapter.generate_image(merge_prompt, quality="hd", init_image_path=composite_path) 
            
            # Suponiendo que el adapter devuelve una clave de S3 (como 'generated/...'), 
            # necesitamos descargarla para el overlay.
            import boto3
            s3 = boto3.client("s3")
            bucket = os.getenv("AWS_STORAGE_BUCKET_NAME")
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_raw:
                tmp_raw_path = tmp_raw.name
                tmp_raw.close() # EVITA WINERROR 32
                s3.download_file(bucket, raw_merged_s3_key, tmp_raw_path)
                
            final_composite_local_path = renderer.apply_final_overlays(tmp_raw_path, panel_list)
            
            # 4. Subir el resultado FINAL (con globos nítidos) a S3
            with open(final_composite_local_path, "rb") as f:
                final_data = f.read()
                final_s3_key = adapter._upload_to_s3(final_data)
            
            merged_results.append({"page_number": page_num, "image_url": final_s3_key})
            print(f"Final organic page with sharp balloons uploaded to: {final_s3_key}")
            
        finally:
            # Limpieza segura
            if os.path.exists(composite_path):
                try: os.remove(composite_path)
                except: pass
            if 'tmp_raw_path' in locals() and os.path.exists(tmp_raw_path):
                try: os.remove(tmp_raw_path)
                except: pass
            if 'final_composite_local_path' in locals() and os.path.exists(final_composite_local_path):
                try: os.remove(final_composite_local_path)
                except: pass
        
    # CRITICO: Debemos devolver los PANELS también para que el backend guarde los globos y URLs de imagen
    return {"merged_pages": merged_results, "panels": state["panels"], "current_step": "done"}

def balloon_generator(state: AgentState):
    print("--- GENERATING DIALOGUE BALLOONS ---")
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    
    # Preparamos los paneles para que el LLM les asigne texto
    panels_context = []
    for p in state["panels"]:
        panels_context.append({
            "id": p.get("id"),
            "scene_description": p.get("scene_description", ""),
            "characters": p.get("characters", [])
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
