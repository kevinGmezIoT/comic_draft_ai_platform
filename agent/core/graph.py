from typing import TypedDict, List, Annotated, Dict
from langgraph.graph import StateGraph, END
from .adapters import get_image_adapter
from .knowledge import KnowledgeManager, CharacterManager, StyleManager, CanonicalStore
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
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
    layout: dict
    balloons: List[dict] = []

class AgentState(TypedDict):
    project_id: str
    sources: List[str]
    max_pages: int
    max_panels: int
    layout_style: str # "dynamic" | "vertical" | "grid"
    world_model_summary: str
    style_guide: str
    full_script: str
    script_outline: List[str]
    panels: List[Panel]
    merged_pages: List[dict] # [{page_number: 1, image_url: "..."}]
    canvas_dimensions: str
    plan_only: bool = False
    current_step: str
    action: str = "generate" # "generate" | "regenerate_panel"
    panel_id: str = None
    continuity_state: Dict[str, Dict] # State tracking for Agent H
    reference_images: List[str]
    global_context: Dict # Optional metadata from backend

class PromptBuilder:
    """Agent F: Prompt Builder - Composes layered prompts for image generation."""
    def __init__(self, project_id: str):
        self.cm = CharacterManager(project_id)
        self.sm = StyleManager(project_id)
        
    def build_panel_prompt(self, panel: Panel, world_summary: str, continuity_state: Dict) -> str:
        # Layer 1: Style Override or Global Style
        panel_style = panel.get("panel_style")
        if panel_style:
            style_part = f"STYLE OVERRIDE: {panel_style}"
        else:
            style_part = self.sm.get_style_prompt()
        
        # Layer 1.5: Instruction Integration
        instructions = panel.get("instructions")
        instr_part = f"ADITONAL INSTRUCTIONS: {instructions}\n" if instructions else ""

        # Layer 2: Characters (Canonical Traits + Continuity)
        char_parts = []
        char_names = panel.get("characters", [])
        for char_name in char_names:
            base_char = self.cm.get_character_prompt_segment(char_name)
            # Add continuity state (Agent H)
            char_state = continuity_state.get(char_name, {})
            state_str = ""
            if char_state:
                state_items = [f"{k}: {v}" for k, v in char_state.items()]
                state_str = f" Estado actual: {', '.join(state_items)}."
            char_parts.append(f"{base_char}{state_str}")
            
        # Layer 3: Scene Action & Setting (Base)
        scene_desc = panel.get('scene_description', 'Cinematic comic scene')
        
        # Layer 4: Composition & Reasoning (Agent F Art Direction)
        layout = panel.get("layout", {"w": 50, "h": 50})
        w, h = layout.get("w", 50), layout.get("h", 50)
        aspect_ratio = "1:1"
        if w / h > 1.2: aspect_ratio = "16:9"
        elif h / w > 1.2: aspect_ratio = "9:16"

        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)
        
        is_edit = panel.get("status") == "editing"
        old_prompt = panel.get("prompt", "")

        if is_edit and instructions:
            reasoning_prompt = f"""
            Actúa como un Director de Arte de Cómics. Estás EDITANDO una viñeta existente.
            
            DESCRIPCIÓN VISUAL ANTERIOR: {old_prompt}
            INSTRUCCIONES DE CAMBIO: {instructions}
            
            NUEVO ESTILO: {style_part}
            ESCENARIO: {panel.get('scenery', 'Basado en la escena')}
            PERSONAJES: {", ".join(char_names) if len(char_names) > 0 else "Sin personaje"}
            CONTEXTO MUNDO: {world_summary[:300]}
            DISEÑO: {w}%x{h}% ({aspect_ratio}).
            RASGOS: {" ".join(char_parts)}
            
            Genera un PROMPT VISUAL FINAL que describa el resultado deseado combinando la descripción original con los cambios solicitados.
            Sé específico sobre qué elementos cambian (ej: "Ahora la ventana está iluminada...") y qué elementos se mantienen.
            Como la imagen original se adjunta, puedes hacer referencia a ella indicando qué debes cambiar.
            Responde ÚNICAMENTE con el prompt en inglés o español.
            """
        else:
            reasoning_prompt = f"""
            Actúa como un Director de Fotografía de Cómics (Agent F: Prompt Builder).
            ESCENA: {scene_desc}
            ESCENARIO: {panel.get('scenery', 'Basado en la descripción de la escena')}
            PERSONAJES: {", ".join(char_names) if len(char_names) > 0 else "Sin personaje"}
            CONTEXTO MUNDO: {world_summary[:300]}
            ESTILO BASE: {style_part}
            DISEÑO PANEL: {w}% de ancho x {h}% de alto ({aspect_ratio}).
            RASGOS CANÓNICOS: {" ".join(char_parts) if len(char_parts) > 0 else "Sin personaje"}
            
            Genera un PROMPT VISUAL FINAL para Stable Diffusion / DALL-E.
            Mejora la composición, iluminación y ángulo de cámara para este layout.
            {instr_part}
            Responde ÚNICAMENTE con el prompt en inglés o español según sea más efectivo para la IA de imagen.
            """
        try:
            visual_prompt = llm.invoke(reasoning_prompt).content.strip()
            return visual_prompt
        except Exception as e:
            print(f"Error in PromptBuilder reasoning: {e}")
            # Fallback a prompt estructurado básico
            return f"{style_part}\nEscena: {scene_desc}. {' '.join(char_parts)}\nCinematic composition {aspect_ratio}."

class ContinuitySupervisor:
    """Agent H: Continuity Supervisor - Tracks and validates state between panels."""
    def __init__(self, project_id: str):
        self.canon = CanonicalStore(project_id)
        
    def update_state(self, current_state: Dict, panel: Panel) -> Dict:
        # Simple LLM logic to update state based on panel action
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        
        prompt = f"""
        Actualiza el estado de continuidad basándote en la acción del panel.
        ESTADO ANTERIOR: {json.dumps(current_state)}
        ACCIÓN DEL PANEL: {panel['scene_description']}
        PERSONAJES: {", ".join(panel.get('characters', []))}
        
        Identifica cambios en: ropa, heridas, objetos en mano, o ubicación.
        Responde en JSON con el nuevo estado consolidado.
        """
        try:
            res = llm.invoke(prompt)
            new_state = json.loads(res.content.replace("```json", "").replace("```", ""))
            return new_state
        except:
            return current_state

def ingest_and_rag(state: AgentState):
    print("--- RAG & INGESTION ---")
    km = KnowledgeManager(state["project_id"])
    vectorstore, image_paths = km.ingest_from_urls(state["sources"])
    
    global_ctx = state.get("global_context", {})
    summary_parts = []
    
    # 1. Prioritize Global Context (Manually entered info)
    if global_ctx.get("description"):
        summary_parts.append(f"SYNOPSIS / DESCRIPTION: {global_ctx['description']}")
    if global_ctx.get("world_bible"):
        summary_parts.append(f"WORLD BIBLE: {global_ctx['world_bible']}")
    if global_ctx.get("style_guide"):
        summary_parts.append(f"STYLE GUIDE: {global_ctx['style_guide']}")
        
    # Append Characters from Context
    if global_ctx.get("characters"):
        char_info = "CHARACTERS:\n" + "\n".join([f"- {c['name']}: {c.get('description', '')}" for c in global_ctx["characters"]])
        summary_parts.append(char_info)
        
    # Append Sceneries from Context
    if global_ctx.get("sceneries"):
        scene_info = "SCENERIES:\n" + "\n".join([f"- {s['name']}: {s.get('description', '')}" for s in global_ctx["sceneries"]])
        summary_parts.append(scene_info)
    
    summary = "\n\n".join(summary_parts)
    full_script = ""
    
    # 2. Augment with RAG if vectorstore exists
    if vectorstore:
        # Extraer info adicional del mundo si no hay suficiente en el contexto
        if not summary:
            world_info = km.query_world_rules("Describe el estilo artístico, personajes principales y escenarios.")
            summary = "\n".join([doc.page_content for doc in world_info])
            
        # Extraer guión (El guión suele venir del documento subido)
        script_info = km.query_world_rules("Extrae el guión completo o la trama detallada de la historia.")
        full_script = "\n".join([doc.page_content for doc in script_info])
    
    # Normalizar estilo (Agent B)
    sm = StyleManager(state["project_id"])
    sm.normalize_style(summary)
    
    return {
        "current_step": "world_model_builder", 
        "world_model_summary": summary,
        "full_script": full_script,
        "reference_images": image_paths
    }

def world_model_builder(state: AgentState):
    print("--- WORLD MODEL BUILDING (Characters & Scenarios) ---")
    cm = CharacterManager(state["project_id"])
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    
    # Pre-cargar personajes conocidos desde el backend si existen
    backend_chars = state.get("global_context", {}).get("characters", [])
    known_character_images = {c["name"].lower(): [c["image_url"]] for c in backend_chars if c.get("image_url")}
    
    prompt = f"""
    Basándote en este resumen del mundo, identifica a los personajes principales.
    Para cada personaje, extrae su nombre en una sola palabra y una descripción física detallada para generación de imágenes.
    
    RESUMEN:
    {state['world_model_summary']}
    
    IMÁGENES DE REFERENCIA DISPONIBLES (archivos): {", ".join([os.path.basename(p) for p in state.get("reference_images", [])])}
    
    Responde en formato JSON:
    {{"characters": [{{"name": "primer nombre del personaje (Una sola palabra)", "description": "..."}}]}}
    """
    
    try:
        response = llm.invoke(prompt)
        content = response.content.strip()
        if content.startswith("```json"):
            content = content[7:-3].strip()
        data = json.loads(content)
        
        ref_images = state.get("reference_images", [])
        
        for char in data.get("characters", []):
            name = char["name"]
            description = char["description"]
            images = []
            
            # 1. Intentar match con backend (Mejorado: match parcial)
            matched_url = None
            for b_name, b_urls in known_character_images.items():
                if name.lower() in b_name or b_name in name.lower():
                    matched_url = b_urls[0]
                    print(f"DEBUG: Character '{name}' matched with backend character '{b_name}'")
                    break
            
            if matched_url:
                images.append(matched_url)
            
            # 2. Intentar match con archivos subidos (via sugerencia del LLM o nombre)
            suggested_file = char.get("suggested_image_file")
            if suggested_file and suggested_file != "null":
                for p in ref_images:
                    if suggested_file in p:
                        images.append(p)
                        print(f"DEBUG: Character '{name}' matched with suggested file '{suggested_file}'")
                        break
            
            # Fallback: buscar por nombre en los archivos
            if not images:
                for p in ref_images:
                    if name.lower() in p.lower():
                        images.append(p)
                        print(f"DEBUG: Character '{name}' matched by name in file '{p}'")
                        break

            unique_images = list(set(images))
            cm.register_character(name, description, unique_images)
            print(f"Registered character: {name} with {len(unique_images)} images. URLs: {unique_images}")
            
    except Exception as e:
        print(f"Error extracting characters: {e}")
        
    return {"current_step": "planner", "continuity_state": {}, "canvas_dimensions": "800x1100 (A4)"}

def planner(state: AgentState):
    existing_panels = state.get("panels", [])
    max_panels = state.get("max_panels")
    
    # Identificar si estamos regenerando una página específica
    target_page = state.get("page_number")
    preserved_panels = []
    
    if target_page:
        # Preservar todos los paneles que NO son de la página objetivo
        preserved_panels = [p for p in existing_panels if p.get("page_number") != target_page]
        print(f"DEBUG: [SCOPED PLANNING] Preserving {len(preserved_panels)} panels from other pages. Target Page: {target_page}")

    if target_page:
        preserved_panels = [p for p in existing_panels if p.get("page_number") != target_page]
        print(f"DEBUG: [SCOPED PLANNING] Preserving {len(preserved_panels)} panels. Target Page: {target_page}")

    # Calcular estructura de páginas basada en los paneles existentes (si los hay)
    page_structure = {}
    if existing_panels:
        for p in existing_panels:
            p_num = p.get("page_number", 1)
            page_structure[p_num] = page_structure.get(p_num, 0) + 1
    
    # Formatear la sugerencia de estructura para el prompt
    structure_str = ""
    if page_structure:
        parts = [f"Página {k}: {v} paneles" for k, v in sorted(page_structure.items())]
        structure_str = f"ESTRUCTURA DE LIENZO ACTUAL (REQUERIDA): {', '.join(parts)}."
    
    print("--- STRATEGIC PLANNING ---")
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)
    
    prompt = f"""
    Basándote en el siguiente SUMMARY del mundo y SCRIPT:
    
    SUMMARY:
    {state['world_model_summary']}
    
    SCRIPT (Separado en páginas y descriciones de viñetas de cada página):
    {state['full_script']}
    
    TAMAÑO DE PÁGINA RECOMENDADO: {state.get('canvas_dimensions', '800x1100 (A4)')}
    ESTILO DE LAYOUT: {state.get('layout_style', 'dynamic')}
    {structure_str}

    {'ESTÁS REGENERANDO ÚNICAMENTE LA PÁGINA ' + str(target_page) if target_page else 'ESTÁS GENERANDO EL CÓMIC COMPLETO'}
    
    ORDEN DE PRIORIDAD:
    - **DISTRIBUCIÓN ESTRICTA**: { 'Sigue exactamente la ESTRUCTURA DE LIENZO ACTUAL indicada arriba.' if structure_str else 'Reparte los ' + str(state.get('max_panels', 'paneles')) + ' entre las ' + str(state.get('max_pages', 3)) + ' páginas.' }
    - **ÍNDICE DE ORDEN (CRÍTICO)**: El campo `order_in_page` DEBE EMPEZAR EN 0 para el primer panel de cada página. (Ej: 0, 1, 2...). No empieces en 1.
    - Si el número total de paneles es {state.get('max_panels', 0)} y tienes {state.get('max_pages', 3)} páginas, asegúrate de que el campo `page_number` avance lógicamente.
    - **CONTINUIDAD**: Si estás generando el cómic completo, el primer panel de la Página 2 debe ser la continuación inmediata del último panel de la Página 1.
    
    FORMATO JSON OBLIGATORIO:
    {{
        "panels": [
            {{
                "page_number": 1,
                "order_in_page": 0,
                "scene_description": "Descripción detallada de la escena...",
                "script": "parte del guión que describe el panel o viñeta",
                "characters": ["Nombre del Personaje"],
                "scenery": "Lugar donde se desarrolla este panel o viñeta",
                "style": "Estilo de dibujo"
            }}
        ]
    }}
    
    Responde ÚNICAMENTE con un JSON válido. No incluyas texto fuera del bloque de código JSON.
    """
    
    try:
        if not state.get('full_script') or len(state['full_script'].strip()) < 5:
            raise ValueError("DEBUG ERROR: El script está vacío o es demasiado corto para planificar.")

        response = llm.invoke([
            SystemMessage(content="Eres un director de arte de cómics experto en descomposición de guiones. Responde SIEMPRE con un JSON válido."),
            HumanMessage(content=prompt)
        ])
        
        content = response.content.strip()
        print(f"DEBUG: LLM Planner Output: {content[:200]}...")

        if content.startswith("```json"):
            content = content[7:-3].strip()
        
        data = json.loads(content)
        
        def find_all_panels(obj):
            found = []
            keys_to_match = ["scene_description", "prompt", "descripcion", "guion", "escena", "accion", "texto", "description", "panel_description"]
            if isinstance(obj, list):
                for item in obj:
                    if isinstance(item, dict) and any(k in item for k in keys_to_match):
                        found.append(item)
                    else:
                        found.extend(find_all_panels(item))
            elif isinstance(obj, dict):
                if any(k in obj for k in keys_to_match):
                    found.append(obj)
                else:
                    for value in obj.values():
                        found.extend(find_all_panels(value))
            return found

        panels = find_all_panels(data)
        if not panels:
            if isinstance(data, list):
                panels = data
        
        if not panels:
             raise ValueError("No panels were generated by the LLM from the script.")

        page_counts = {}
        # Crear un mapa de layouts existentes para preservación (heurística de posición)
        existing_layout_map = {
            (p.get("page_number"), p.get("order_in_page")): p.get("layout") 
            for p in existing_panels 
            if p.get("layout") and p.get("layout").get("w", 0) > 0
        }

        for i, p in enumerate(panels):
            # Standardize ID as string to avoid type mismatch (int vs str)
            p_id = str(p.get("id")) if p.get("id") else f"p_{i}"
            p["id"] = p_id
            p.setdefault("image_url", "")
            p.setdefault("status", "pending")
            p.setdefault("characters", [])
            
            p_num = target_page if target_page else p.get("page_number", 1)
            p["page_number"] = p_num
            p_order = page_counts.get(p_num, 0)
            p["order_in_page"] = p_order
            page_counts[p_num] = p_order + 1

            # Intentar recuperar layout previo si coincide la posición
            prev_layout = existing_layout_map.get((p_num, p_order))
            if prev_layout:
                print(f"DEBUG: [PLANNER] Inheriting Layout for Pág {p_num}, Orden {p_order} -> {prev_layout}")
                p["layout"] = prev_layout
            else:
                p.setdefault("layout", {})
            
            if not p.get("prompt"):
                p["prompt"] = "Cinematic comic panel"

        final_panels = preserved_panels + panels
        return {"panels": final_panels, "current_step": "layout_designer"}
    except Exception as e:
        print(f"CRITICAL ERROR en planner: {e}")
        import traceback
        traceback.print_exc()
        raise e

def image_generator(state: AgentState):
    print("--- AGENT F & H: MULTIMODAL IMAGE GENERATION ---")
    adapter = get_image_adapter()
    pb = PromptBuilder(state["project_id"])
    cs = ContinuitySupervisor(state["project_id"])
    
    updated_panels = []
    continuity = state.get("continuity_state", {})
    
    sorted_panels = sorted(state["panels"], key=lambda x: (x.get('page_number', 1), x.get('order_in_page', 0)))
    
    # Identificar personajes y sus imágenes de referencia para contexto multimodal
    cm = pb.cm # Usar el CharacterManager de PromptBuilder
    
    target_panel_id = str(state.get("panel_id")) if state.get("panel_id") else None

    for panel in sorted_panels:
        # Si es regeneración selectiva, saltar si no es el ID objetivo
        if state.get("action") == "regenerate_panel" and target_panel_id:
            if str(panel.get("id")) != target_panel_id:
                updated_panels.append(panel)
                continue

        if panel.get("image_url") and panel.get("status") not in ["pending", "editing"]:
            updated_panels.append(panel)
            continue

        # Agent H: Update continuity based on the action
        continuity = cs.update_state(continuity, panel)
        
        # Agent F: Build Layered Prompt
        augmented_prompt = pb.build_panel_prompt(panel, state["world_model_summary"], continuity)
        
        # Coleccionar imágenes de contexto (Personajes del panel + Imagen de Referencia)
        context_images = []
        for char_name in panel.get("characters", []):
            char_refs = cm.get_character_images(char_name)
            if char_refs:
                context_images.extend(char_refs)
        
        # Add reference image from Panel context if available
        ref_img = panel.get("reference_image_url")
        if ref_img:
            context_images.append(ref_img)
        
        # Eliminar duplicados manteniendo orden
        seen = set()
        unique_context = [x for x in context_images if not (x in seen or seen.add(x))]
        
        print(f"DEBUG: Panel {panel['id']} Context Images ({len(unique_context)}): {unique_context}")
        print(f"DEBUG: Augmented Prompt: {augmented_prompt[:150]}...")
        print(f"DEBUG: Style Prompt: {panel.get('panel_style')}")

        # Image Generation
        layout = panel.get("layout", {"w": 50, "h": 50})
        w, h = layout.get("w", 50), layout.get("h", 50)
        aspect_ratio = "1:1"
        if w / h > 1.2: aspect_ratio = "16:9"
        elif h / w > 1.2: aspect_ratio = "9:16"

        # Image-to-Image support if current_image_url is provided or fallback to existing image_url
        init_image = panel.get("current_image_url") or panel.get("image_url")

        if panel.get("status") == "editing" and init_image:
            # Usamos edit_image para que el adapter gestione la descarga de la URL antes de procesar
            print(f"DEBUG: Editing panel {panel['id']} using init_image: {init_image}")
            url = adapter.edit_image(original_image_url=init_image, prompt=augmented_prompt, style_prompt=panel.get('panel_style'))
        else:
            url = adapter.generate_panel(augmented_prompt, style_prompt=panel.get('panel_style'), aspect_ratio=aspect_ratio, context_images=unique_context)
            
        panel["image_url"] = url
        panel["status"] = "generated"
        panel["prompt"] = augmented_prompt
        updated_panels.append(panel)
        
    return {"panels": updated_panels, "continuity_state": continuity, "current_step": "balloons"}

def layout_designer(state: AgentState):
    print("--- DEFINING PAGE LAYOUTS (Templates) ---")
    panels = state.get("panels", [])
    if not panels:
        print("--- WARNING: No panels to design layout for. ---")
        return {"current_step": "generator"}
    
    # Solo diseñamos layout para los que les falte
    panels_needing_layout = []
    for p in panels:
        ly = p.get("layout", {})
        px_w = ly.get("w", 0)
        if not (ly and px_w and float(px_w) > 0):
            panels_needing_layout.append(p)
    
    print(f"DEBUG: Total panels: {len(panels)}, Panels needing layout: {len(panels_needing_layout)}")
    
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
            ly = p.get("layout", {})
            # Aceptamos tanto 'w' como 'width' por si acaso, y validamos que sea mayor a 0
            w_val = ly.get("w") or ly.get("width")
            try:
                if w_val and float(w_val) > 0:
                    print(f"DEBUG: [LAYOUT DESIGNER] Preservando Layout Panel {p.get('id')} -> x:{ly.get('x')}, y:{ly.get('y')}, w:{w_val}, h:{ly.get('h')}")
                    updated_panels.append(p)
                    continue
            except (ValueError, TypeError):
                pass

            print(f"DEBUG: [LAYOUT DESIGNER] Diseñando Layout para Panel {p.get('id')} (Pág {page_num}, Index {i})")

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
    
    # Salvaguarda: Asegurarse de no perder ningún panel del estado original
    accounted_ids = set(str(p.get("id")) for p in updated_panels)
    for p in panels:
        if str(p.get("id")) not in accounted_ids:
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
    
        
    last_page_s3_key = None
    sorted_page_nums = sorted(pages.keys(), key=int)
    
    for page_num in sorted_page_nums:
        panel_list = pages[page_num]
        print(f"Merging Page {page_num}...")
        
        # 1. Crear el collage base con globos (como guía para la IA)
        composite_path = renderer.create_composite_page(panel_list, include_balloons=True)
        
        # 1.5. Análisis Multimodal para Blend (Uso de Gemini con Fallback)
        import base64
        with open(composite_path, "rb") as f:
            composite_b64 = base64.b64encode(f.read()).decode("utf-8")
        
        vision_prompt = "Esta es una maqueta de una página de cómic con paneles y globos. Describe cómo deberían mezclarse los fondos de manera artística y orgánica para que parezca una sola ilustración fluida, manteniendo la posición de los personajes y globos."

        def get_visual_blend_description(b64_image, prompt):
            # Intentar primero con Gemini 2.0 Flash, luego 1.5 Flash, y finalmente GPT-4o-mini
            models_to_try = [
                ("google", "gemini-2.0-flash"),
                ("google", "gemini-1.5-flash"),
                ("openai", "gpt-4o-mini")
            ]
            
            last_error = None
            for provider, model_name in models_to_try:
                try:
                    print(f"DEBUG: Attempting visual analysis with {model_name}...")
                    if provider == "google":
                        llm = ChatGoogleGenerativeAI(model=model_name, temperature=0.2)
                    else:
                        llm = ChatOpenAI(model=model_name, temperature=0.2)
                        
                    message = HumanMessage(
                        content=[
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{b64_image}"},
                            },
                        ]
                    )
                    response = llm.invoke([message])
                    return response.content
                except Exception as e:
                    print(f"WARNING: Model {model_name} failed: {e}")
                    last_error = e
                    continue
            
            print(f"ERROR: All models failed for vision analysis. Fallback to default prompt. Last error: {last_error}")
            return "Blend the backgrounds smoothly."

        visual_blend_description = get_visual_blend_description(composite_b64, vision_prompt)
        print(f"Visual Blend Insight: {visual_blend_description[:100]}...")

        merge_prompt = f"ORGANIC COMIC PAGE MERGE. \nInstrucciones visuales: {visual_blend_description} \nPágina en el guión: {page_num}\nStyle: {state.get('world_model_summary', '')}. Professional comic art style."
        
        # CONTINUIDAD: Agregar la página anterior como referencia visual si existe
        merge_context_images = []
        bucket = os.getenv("AWS_STORAGE_BUCKET_NAME")

        if last_page_s3_key:
            prev_s3_uri = f"s3://{bucket}/{last_page_s3_key}"
            print(f"DEBUG: Adding previous page (Pág {int(page_num)-1}) as continuity context: {prev_s3_uri}")
            merge_context_images.append(prev_s3_uri)
        
        # También pasar opcionalmente el composite actual como contexto (como pide el usuario)
        # s3:// temporary local paths don't work in context_images unless uploaded, 
        # but the adapter can handle local paths too.
        merge_context_images.append(composite_path)

        try:
            # 2. Generar mezcla orgánica via Image-to-Image (especializado para fusión)
            raw_merged_s3_key = adapter.generate_page_merge(
                merge_prompt, 
                init_image_path=composite_path, 
                context_images=merge_context_images
            ) 
            
            # Guardamos esta página para que sea referencia de la siguiente
            last_page_s3_key = raw_merged_s3_key
            
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
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    
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
        
        # Mapear balloons de vuelta a los paneles usando IDs como strings
        balloons_map = {str(p["id"]): p["balloons"] for p in data.get("panels", [])}
        
        updated_panels = []
        for p in state["panels"]:
            p_id = str(p["id"])
            p["balloons"] = balloons_map.get(p_id, [])
            print(f"DEBUG: Panel {p_id} got {len(p['balloons'])} balloons.")
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

    # Router de entrada para regeneración selectiva
    def router_entry(state: AgentState):
        if state.get("action") == "regenerate_panel":
            return "generator"
        if state.get("action") == "regenerate_merge":
            return "merger"
        return "ingest"

    workflow.set_conditional_entry_point(
        router_entry,
        {
            "generator": "generator",
            "merger": "merger",
            "ingest": "ingest"
        }
    )

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

    # Para regeneración selectiva, después del generador terminamos (o podemos seguir a globos si quisiéramos)
    def post_generator_router(state: AgentState):
        if state.get("action") == "regenerate_panel":
            return "end"
        return "continue"

    workflow.add_conditional_edges(
        "generator",
        post_generator_router,
        {
            "end": END,
            "continue": "balloons"
        }
    )

    workflow.add_edge("balloons", "merger")
    workflow.add_edge("merger", END)

    return workflow.compile()
