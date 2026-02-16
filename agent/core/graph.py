from typing import TypedDict, List, Annotated, Dict
from langgraph.graph import StateGraph, END
from .adapters import get_image_adapter
from .knowledge import KnowledgeManager, CharacterManager, StyleManager, SceneryManager, CanonicalStore
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
    current_image_url: str = None # Context for I2I
    reference_image_url: str = None # Visual reference context
    continuity_state: Dict[str, Dict] # State tracking for Agent H
    reference_images: List[str]
    global_context: Dict # Optional metadata from backend
    page_summaries: Dict[int, str] # Per-page detailed summaries from story understanding
    panel_purposes: Dict[str, str] # Panel key -> underlying purpose/intent

class PromptBuilder:
    """Agent F: Prompt Builder - Composes layered prompts for image generation."""
    def __init__(self, project_id: str):
        self.canon = CanonicalStore(project_id)
        self.cm = CharacterManager(project_id, canon=self.canon)
        self.sm = StyleManager(project_id, canon=self.canon)
        self.scm = SceneryManager(project_id, canon=self.canon)
        
    def build_panel_prompt(self, panel: Panel, world_summary: str, continuity_state: Dict) -> str:
        # Layer 1: Style Override or Global Style
        panel_style = panel.get("panel_style")
        if panel_style:
            style_part = f"STYLE OVERRIDE: {panel_style}"
        else:
            style_part = self.sm.get_style_prompt()
        
        # Layer 1.5: Instruction Integration
        instructions = panel.get("instructions")
        instr_part = f"ADDITIONAL INSTRUCTIONS: {instructions}\n" if instructions else ""

        # Layer 2: Characters (Canonical Traits + Continuity)
        char_parts = []
        char_names = panel.get("characters", [])
        
        # Continuity data for characters and environment
        characters_continuity = continuity_state.get("characters", {})
        environment_continuity = continuity_state.get("environment", {})
        
        for char_name in char_names:
            base_char = self.cm.get_character_prompt_segment(char_name)
            # Add continuity state (Agent H)
            # Try both the specific name and a case-insensitive match
            char_state = characters_continuity.get(char_name)
            if not char_state:
                # Fallback: look for case-insensitive match
                for name_key, state in characters_continuity.items():
                    if name_key.lower() == char_name.lower():
                        char_state = state
                        break
            
            state_str = ""
            if char_state and isinstance(char_state, dict):
                state_items = [f"{k}: {v}" for k, v in char_state.items() if v]
                if state_items:
                    state_str = f" [Continuidad: {', '.join(state_items)}]"
            char_parts.append(f"{base_char}{state_str}")
            
        # Layer 3: Scene Action & Setting (Base + Scenario Continuity)
        base_scenery_name = panel.get('scenery', 'Ambientación general')
        scenery_base_prompt = self.scm.get_scenery_prompt_segment(base_scenery_name)
        
        env_str = ""
        if environment_continuity:
            # Flatten environmental details if they are nested
            def flatten_env(d, prefix=""):
                items = []
                for k, v in d.items():
                    if isinstance(v, dict):
                        items.extend(flatten_env(v, f"{k} "))
                    else:
                        items.append(f"{prefix}{k}: {v}")
                return items
            
            env_details = flatten_env(environment_continuity)
            if env_details:
                env_str = f" (Detalles de continuidad del entorno: {', '.join(env_details)})"
        
        scene_desc = panel.get('scene_description', 'Cinematic comic scene')
        final_scenery = f"{scenery_base_prompt}{env_str}"
        
        # Layer 4: Composition & Reasoning (Agent F Art Direction)
        layout = panel.get("layout", {"w": 50, "h": 50})
        w, h = layout.get("w", 50), layout.get("h", 50)
        aspect_ratio = "1:1"
        if w / h > 1.2: aspect_ratio = "16:9"
        elif h / w > 1.2: aspect_ratio = "9:16"

        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)
        
        is_edit = panel.get("status") == "editing"
        old_prompt = panel.get("prompt", "")

        char_parts_str = "\n".join(char_parts) if len(char_parts) > 0 else "No hay personajes principales en escena"
        
        if is_edit and instructions:
            reasoning_prompt = f"""
            Actúa como un Director de Arte de Cómics. Estás EDITANDO una viñeta existente.
            
            DESCRIPCIÓN VISUAL ORIGINAL:\n {old_prompt}
            INSTRUCCIONES DE CAMBIO: {instructions}
            
            DISEÑO: {w}%x{h}% ({aspect_ratio}).
            CONTEXTO MUNDO: {world_summary[:500]}
            
            REGLAS CANÓNICAS DE APARIENCIA (ESTRICTO): 
            ---
            SCENERY:
            {final_scenery}
            
            CHARACTERS:
            {char_parts_str}
            ---
            
            Genera un PROMPT VISUAL FINAL que describa el resultado deseado combinando la descripción original con los cambios solicitados.
            Sé específico sobre qué elementos cambian (ej: "Ahora la ventana está iluminada...") y qué elementos se mantienen.
            Como la imagen original se adjunta, puedes hacer referencia a ella indicando qué debes cambiar.
            Responde ÚNICAMENTE con el prompt en inglés o español.
            """
        else:
            reasoning_prompt = f"""
            Actúa como un Director de Fotografía de Cómics (Agent F: Prompt Builder).
            
            ESCENA: {scene_desc}
            ESTILO BASE: {style_part}
            DISEÑO PANEL: {w}% de ancho x {h}% de alto ({aspect_ratio}).
            CONTEXTO MUNDO: {world_summary[:500]}
            
            REGLAS CANÓNICAS DE APARIENCIA (ESTRICTO):
            ---
            SCENERY:
            {final_scenery}
            
            CHARACTERS:
            {char_parts_str}
            ---
            
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
        Actualiza el estado de continuidad del cómic basándote en la acción de la nueva viñeta.
        
        ESTADO ACTUAL (JSON):
        {json.dumps(current_state, indent=2)}
        
        NUEVA ACCIÓN:
        {panel['scene_description']}
        
        PERSONAJES PRESENTES: {", ".join(panel.get('characters', []))}
        
        Instrucciones:
        1. Identifica cambios en: ropa, heridas, objetos en mano, ubicación o estado del entorno.
        2. Para el 'environment', sé específico sobre la zona del escenario (ej: 'escritorio', 'junto a la puerta') para mantener la lógica espacial.
        3. Mantén la consistencia con el estado anterior si no hay cambios.
        4. Responde ÚNICAMENTE con un JSON que tenga esta estructura exacta:
        {{
            "characters": {{
                "NombrePersonaje": {{ "ropa": "...", "heridas": "...", "objetos": "...", "ubicación_exacta": "..." }}
            }},
            "environment": {{
                "zona": "...", "iluminacion": "...", "objetos_movidos": "...", "detalles_persistentes": "..."
            }}
        }}

        Usa llaves en inglés para el JSON ("characters", "environment") pero puedes usar español para los valores.
        """
        try:
            res = llm.invoke(prompt)
            content = res.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
                
            new_state = json.loads(content)
            
            # Normalización mínima de claves si el LLM usó español por error en las raíces
            if "personajes" in new_state and "characters" not in new_state:
                new_state["characters"] = new_state.pop("personajes")
            if "habitacion" in new_state and "environment" not in new_state:
                new_state["environment"] = new_state.pop("habitacion")
            if "estado" in new_state and len(new_state) == 1:
                # Si envolvió todo en "estado", lo sacamos
                return self.update_state(current_state, panel) # Re-intento simple o desempaquetado
            
            return new_state
        except Exception as e:
            print(f"Error updating continuity state: {e}")
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
    
    # Decidir qué usar para normalizar el estilo
    # Prioridad: 1. style_guide directa, 2. world_bible, 3. fragmento de summary (solo si es necesario)
    style_input = global_ctx.get("style_guide") or global_ctx.get("world_bible")
    
    # Solo normalizar si hay una guía explícita o si el estilo actual es el por defecto
    current_style = sm.get_style_prompt()
    is_default = "Professional comic book" in current_style
    
    if style_input:
        print(f"DEBUG: [Agent B] Normalizing style using explicit guide. Input length: {len(style_input)}")
        sm.normalize_style(style_input)
    elif is_default and summary:
        # Si no hay guía pero hay resumen, intentamos extraer estilo del inicio del resumen (reglas base)
        print("DEBUG: [Agent B] Normalizing style using world summary excerpt.")
        sm.normalize_style(summary[:1000])
    else:
        print("DEBUG: [Agent B] Skipping style normalization (already set or no input available).")
    
    return {
        "current_step": "story_understanding", 
        "world_model_summary": summary,
        "full_script": full_script,
        "reference_images": image_paths
    }

def story_understanding(state: AgentState):
    """Story Understanding Node: Reads the full script in batches and extracts
    1. Detailed page summaries (heuristic analysis)
    2. Underlying panel/vignette purposes
    Designed to handle scripts of 100+ pages via chunked processing."""
    print("--- STORY UNDERSTANDING (Deep Script Analysis) ---")
    
    full_script = state.get("full_script", "")
    sources = state.get("sources", [])
    project_id = state.get("project_id")
    
    # ── Step 1: Obtain raw pages from the PDF (or fallback to text chunks) ──
    raw_pages: Dict[int, str] = {}  # page_number -> text content
    
    # Try to load pages directly from the PDF source for page-level fidelity
    pdf_loaded = False
    for url in sources:
        ext = os.path.splitext(url.split('?')[0])[1].lower()
        if ext == '.pdf':
            try:
                km = KnowledgeManager(project_id)
                if url.startswith("s3://"):
                    local_path = km._download_from_s3(url)
                elif url.startswith("http"):
                    from urllib.parse import urlparse
                    parsed = urlparse(url)
                    hostname = parsed.netloc
                    if hostname.endswith(".amazonaws.com"):
                        parts = hostname.split('.')
                        if "s3" in parts:
                            bucket_name = parts[0]
                            key = parsed.path.lstrip('/')
                            s3_uri = f"s3://{bucket_name}/{key}"
                            local_path = km._download_from_s3(s3_uri)
                        else:
                            continue
                    else:
                        import requests as req
                        temp_dir = "./data/temp_downloads"
                        os.makedirs(temp_dir, exist_ok=True)
                        local_path = os.path.join(temp_dir, os.path.basename(parsed.path))
                        r = req.get(url, stream=True, timeout=60)
                        r.raise_for_status()
                        with open(local_path, 'wb') as f:
                            for chunk in r.iter_content(chunk_size=8192):
                                f.write(chunk)
                else:
                    local_path = url
                
                from langchain_community.document_loaders import PyPDFLoader
                loader = PyPDFLoader(local_path)
                pages = loader.load()
                for doc in pages:
                    pg = doc.metadata.get("page", 0) + 1  # 1-indexed
                    raw_pages[pg] = doc.page_content
                pdf_loaded = True
                print(f"DEBUG: [StoryUnderstanding] Loaded {len(raw_pages)} pages from PDF.")
                break  # Only process first PDF found
            except Exception as e:
                print(f"WARNING: [StoryUnderstanding] Could not load PDF pages: {e}")
    
    # Fallback: split full_script into synthetic pages if no PDF loaded
    if not pdf_loaded and full_script:
        print("DEBUG: [StoryUnderstanding] No PDF pages loaded; splitting full_script into synthetic pages.")
        CHARS_PER_PAGE = 3000
        for i in range(0, len(full_script), CHARS_PER_PAGE):
            page_num = (i // CHARS_PER_PAGE) + 1
            raw_pages[page_num] = full_script[i:i + CHARS_PER_PAGE]
    
    if not raw_pages:
        print("WARNING: [StoryUnderstanding] No script content to analyze. Skipping.")
        return {
            "current_step": "world_model_builder",
            "page_summaries": {},
            "panel_purposes": {}
        }
    
    total_pages = len(raw_pages)
    print(f"DEBUG: [StoryUnderstanding] Total pages to analyze: {total_pages}")
    
    # ── Step 2: Batch processing – analyze pages in groups of BATCH_SIZE ──
    BATCH_SIZE = 10  # Process 10 pages at a time to stay within context limits
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    
    page_summaries: Dict[int, str] = {}
    panel_purposes: Dict[str, str] = {}  # key: "page_{n}_panel_{m}" -> purpose
    
    sorted_page_nums = sorted(raw_pages.keys())
    
    for batch_start in range(0, len(sorted_page_nums), BATCH_SIZE):
        batch_page_nums = sorted_page_nums[batch_start:batch_start + BATCH_SIZE]
        batch_text = ""
        for pg in batch_page_nums:
            batch_text += f"\n\n=== PÁGINA {pg} ===\n{raw_pages[pg]}"
        
        print(f"DEBUG: [StoryUnderstanding] Processing batch: pages {batch_page_nums[0]}-{batch_page_nums[-1]} ({len(batch_text)} chars)")
        
        prompt = f"""
        Actúa como un Analista de Guiones de Cómic experto.
        
        Tu tarea es leer el siguiente fragmento de guión (páginas {batch_page_nums[0]} a {batch_page_nums[-1]}) y producir DOS tipos de análisis:
        
        ### 1. RESUMEN DETALLADO POR PÁGINA
        Para cada página del fragmento, genera un resumen visual detallado que describa:
        - Qué sucede narrativamente (acción, diálogo clave, progresión dramática).
        - El tono emocional dominante (tensión, calma, humor, misterio, etc.).
        - Los elementos visuales clave que un artista necesitaría saber.
        - Transiciones importantes respecto a la página anterior (si aplica).
        
        ### 2. PROPÓSITO SUBYACENTE DE CADA VIÑETA/PANEL
        Identifica cada viñeta o panel descrito en el guión y asígnale un "propósito subyacente":
        - ¿Cuál es la intención narrativa de esta viñeta? (ej: "Establecer la soledad del personaje",
          "Mostrar la magnitud del escenario", "Revelar un giro argumental", "Generar tensión antes del clímax").
        - ¿Qué emoción debe evocar en el lector?
        - ¿Qué elemento visual es el foco principal?
        
        TEXTO DEL GUIÓN:
        {batch_text}
        
        Responde ÚNICAMENTE en JSON con esta estructura:
        {{
            "page_summaries": {{
                "<número_de_página>": "Resumen detallado de la página..."
            }},
            "panel_purposes": {{
                "page_<N>_panel_<M>": "Propósito subyacente: ..."
            }}
        }}
        
        REGLAS:
        - Para panel_purposes, usa la convención "page_N_panel_M" donde N es el número de página y M empieza en 1.
        - Si una página no tiene viñetas claramente definidas, trata toda la página como un solo panel.
        - Sé preciso y detallado en los resúmenes. Un buen resumen tiene 3-5 oraciones.
        - Los propósitos deben ser concisos (1-2 oraciones) pero específicos.
        """
        
        try:
            response = llm.invoke([
                SystemMessage(content="Eres un analista experto de guiones de cómic. Responde siempre en JSON válido."),
                HumanMessage(content=prompt)
            ])
            
            content = response.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            batch_data = json.loads(content)
            
            # Merge page summaries
            for pg_str, summary in batch_data.get("page_summaries", {}).items():
                try:
                    page_summaries[int(pg_str)] = summary
                except (ValueError, TypeError):
                    page_summaries[pg_str] = summary
            
            # Merge panel purposes
            panel_purposes.update(batch_data.get("panel_purposes", {}))
            
            print(f"DEBUG: [StoryUnderstanding] Batch done. Summaries so far: {len(page_summaries)}, Purposes so far: {len(panel_purposes)}")
            
        except Exception as e:
            print(f"ERROR: [StoryUnderstanding] Batch {batch_page_nums[0]}-{batch_page_nums[-1]} failed: {e}")
            # Fallback: store raw text as summary for these pages
            for pg in batch_page_nums:
                page_summaries[pg] = raw_pages[pg][:500] + "..." if len(raw_pages[pg]) > 500 else raw_pages[pg]
    
    # Reconstruir full_script en orden correcto de páginas para que el planner lo reciba ordenado
    # (el full_script original viene de RAG similarity_search que no respeta orden de páginas)
    ordered_full_script = ""
    for pg in sorted(raw_pages.keys()):
        ordered_full_script += f"\n\n=== PÁGINA {pg} ===\n{raw_pages[pg]}"
    
    print(f"DEBUG: [StoryUnderstanding] ✓ Complete. {len(page_summaries)} page summaries, {len(panel_purposes)} panel purposes extracted. full_script reordered ({len(ordered_full_script)} chars).")
    
    return {
        "current_step": "world_model_builder",
        "page_summaries": page_summaries,
        "panel_purposes": panel_purposes,
        "full_script": ordered_full_script.strip()
    }

def world_model_builder(state: AgentState):
    print("--- WORLD MODEL BUILDING (Characters & Scenarios) ---")
    canon = CanonicalStore(state["project_id"])
    cm = CharacterManager(state["project_id"], canon=canon)
    scm = SceneryManager(state["project_id"], canon=canon)
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    
    # Pre-cargar personajes y escenarios conocidos desde el backend si existen
    backend_chars = state.get("global_context", {}).get("characters", [])
    backend_scenes = state.get("global_context", {}).get("sceneries", [])
    
    known_character_images = {c["name"].lower(): c.get("image_urls", [c["image_url"]] if c.get("image_url") else []) for c in backend_chars}
    known_scenery_images = {s["name"].lower(): s.get("image_urls", [s["image_url"]] if s.get("image_url") else []) for s in backend_scenes}
    
    # 1. Registrar OBLIGATORIAMENTE los personajes y escenarios del wizard (backend)
    for b_char in backend_chars:
        name = b_char["name"]
        description = b_char.get("description", "")
        img_urls = b_char.get("image_urls", [b_char["image_url"]] if b_char.get("image_url") else [])
        cm.register_character(name, description, img_urls)
        print(f"DEBUG: [Wizard Asset] Character '{name}' registered from backend with {len(img_urls)} images.")

    for b_scene in backend_scenes:
        name = b_scene["name"]
        description = b_scene.get("description", "")
        img_urls = b_scene.get("image_urls", [b_scene["image_url"]] if b_scene.get("image_url") else [])
        scm.register_scenery(name, description, img_urls)
        print(f"DEBUG: [Wizard Asset] Scenery '{name}' registered from backend with {len(img_urls)} images.")

    # Recargar listas actualizadas del canon para el prompt
    existing_chars = list(cm.canon.data.get("characters", {}).keys())
    existing_scenes = list(scm.canon.data.get("sceneries", {}).keys())
    original_names_map = cm.canon.data.get("metadata", {}).get("original_keys", {})
    
    display_chars = [original_names_map.get(k, k) for k in existing_chars]
    display_scenes = [original_names_map.get(k, k) for k in existing_scenes]

    prompt = f"""
    Basándote en este resumen del mundo, identifica a los personajes principales y los escenarios clave.
    
    RESUMEN:
    {state['world_model_summary']}
    
    ACTIVOS YA REGISTRADOS (USA ESTOS NOMBRES EXACTOS SI COINCIDEN O DESCRÍBELOS MEJOR):
    - Personajes: {', '.join(display_chars) if display_chars else "Ninguno"}
    - Escenarios: {', '.join(display_scenes) if display_scenes else "Ninguno"}
    
    IMÁGENES DE REFERENCIA DISPONIBLES (archivos): {", ".join([os.path.basename(p) for p in state.get("reference_images", [])])}
    
    Responde en formato JSON:
    {{
        "characters": [{{"name": "nombre (Respetar nombres ya listados)", "description": "..."}}],
        "sceneries": [{{"name": "nombre (Respetar nombres ya listados)", "description": "descripción visual detallada"}}]
    }}
    """
    
    try:
        response = llm.invoke(prompt)
        content = response.content.strip()
        if content.startswith("```json"):
            content = content[7:-3].strip()
        data = json.loads(content)
        
        ref_images = state.get("reference_images", [])
        
        # Ingest Characters
        for char in data.get("characters", []):
            name = char["name"]
            description = char["description"]
            images = []
            
            # Match logic for characters
            # Usar fuzzy matching para ver si ya existe en el canon
            name_canon, existing_char = cm._find_character(name)
            target_name = name_canon if name_canon else name
            
            if existing_char:
                # Si existe, preservamos descripción e imágenes previas si no vienen nuevas
                images = existing_char.get("ref_images", [])
            
            # Intentar mapear imágenes del backend
            for b_name, b_urls in known_character_images.items():
                if target_name.lower() in b_name or b_name in target_name.lower():
                    for url in b_urls:
                        if url and url not in images:
                            images.append(url)
                    break
            
            # Buscar en archivos de referencia si aún no hay imágenes
            if not images:
                for p in ref_images:
                    # Normalización básica para matching de archivos: "nombre personaje" -> "nombrepersonaje"
                    clean_name = target_name.lower().replace(" ", "").replace("_", "")
                    clean_path = os.path.basename(p).lower().replace(" ", "").replace("_", "")
                    if clean_name in clean_path:
                        images.append(p)
                        break

            cm.register_character(target_name, description, list(set(images)))
            
        # Ingest Sceneries
        for scene in data.get("sceneries", []):
            name = scene["name"]
            description = scene["description"]
            images = []
            
            # Usar fuzzy matching para ver si ya existe en el canon
            name_canon, existing_scene = scm._find_scenery(name)
            target_name = name_canon if name_canon else name

            if existing_scene:
                images = existing_scene.get("ref_images", [])
            
            # 1. Match con backend
            for b_name, b_urls in known_scenery_images.items():
                if target_name.lower() in b_name or b_name in target_name.lower():
                    for url in b_urls:
                        if url and url not in images:
                            images.append(url)
                    print(f"DEBUG: Scenery '{target_name}' matched with backend scenery '{b_name}' ({len(b_urls)} images)")
                    break
            
            # 2. Match con archivos por nombre
            if not images:
                for p in ref_images:
                    clean_name = target_name.lower().replace(" ", "").replace("_", "")
                    clean_path = os.path.basename(p).lower().replace(" ", "").replace("_", "")
                    if clean_name in clean_path:
                        images.append(p)
                        print(f"DEBUG: Scenery '{target_name}' matched by name in file '{p}'")
                        break
            
            scm.register_scenery(target_name, description, list(set(images)))
            print(f"Registered scenery: {target_name} with {len(images)} images.")
            
    except Exception as e:
        print(f"Error extracting world elements: {e}")
        
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
    
    print("--- STRATEGIC PLANNING (Batched) ---")
    canon = CanonicalStore(state["project_id"])
    cm = CharacterManager(state["project_id"], canon=canon)
    scm = SceneryManager(state["project_id"], canon=canon)
    
    # Obtener nombres existentes para estandarización
    existing_chars = list(cm.canon.data.get("characters", {}).keys())
    existing_scenes = list(scm.canon.data.get("sceneries", {}).keys())
    
    assets_context = ""
    if existing_chars or existing_scenes:
        assets_context = "LISTA DE ACTIVOS EXISTENTES (USA ESTOS NOMBRES EXACTOS):\n"
        if existing_chars:
            assets_context += f"- PERSONAJES: {', '.join(existing_chars)}\n"
        if existing_scenes:
            assets_context += f"- ESCENARIOS: {', '.join(existing_scenes)}\n"
        assets_context += "Si el guión requiere un escenario o personaje que no está en esta lista, intenta usar el más parecido o crea uno nuevo solo si es estrictamente necesario.\n"

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)
    
    if not state.get('full_script') or len(state['full_script'].strip()) < 5:
        raise ValueError("DEBUG ERROR: El script está vacío o es demasiado corto para planificar.")

    # ── Build page-level script chunks for batched planning ──
    # Use raw full_script split into pages (preserves granular viñeta details)
    # page_summaries from story_understanding are added as supplementary narrative context
    page_summaries = state.get("page_summaries", {})
    full_script = state.get("full_script", "")
    
    script_pages: dict = {}  # page_num -> raw text
    
    # Split raw script into page-sized chunks (keeps panel/viñeta granularity)
    CHARS_PER_PAGE = 3000
    for i in range(0, len(full_script), CHARS_PER_PAGE):
        page_num = (i // CHARS_PER_PAGE) + 1
        script_pages[page_num] = full_script[i:i + CHARS_PER_PAGE]
    print(f"DEBUG: [PLANNER] Split full_script into {len(script_pages)} page chunks for planning.")
    
    # ── Determine batching strategy ──
    max_pages_comic = state.get("max_pages", 3)
    max_panels_comic = state.get("max_panels", 0)
    sorted_script_pages = sorted(script_pages.keys())
    
    # Calculate panels per comic page for distribution guidance
    panels_per_page = max(1, max_panels_comic // max_pages_comic) if max_panels_comic and max_pages_comic else 3
    
    # If the script is short enough (≤10 pages), process in a single call for better coherence
    BATCH_SIZE = 10
    use_batching = len(sorted_script_pages) > BATCH_SIZE
    
    if use_batching:
        print(f"DEBUG: [PLANNER] Large script detected ({len(sorted_script_pages)} pages). Using batched planning.")
    else:
        print(f"DEBUG: [PLANNER] Script fits in single call ({len(sorted_script_pages)} pages).")
    
    # Build supplementary narrative context from page_summaries (if available)
    def get_narrative_context_for_pages(page_nums: list) -> str:
        """Get narrative summaries as supplementary context for a set of script pages."""
        if not page_summaries:
            return ""
        context_parts = []
        for pg in page_nums:
            summary = page_summaries.get(pg, page_summaries.get(str(pg), ""))
            if summary:
                context_parts.append(f"Pág {pg}: {summary}")
        if context_parts:
            return "CONTEXTO NARRATIVO (resumen de las páginas del guión):\n" + "\n".join(context_parts)
        return ""
    
    # ── Helper: invoke LLM for a batch of script pages ──
    def plan_batch(batch_script_text: str, narrative_context: str, comic_page_start: int, comic_page_end: int, 
                   panels_for_batch: int, previous_panel_context: str) -> list:
        """Generate panels for a subset of comic pages from a batch of script text."""
        
        batch_prompt = f"""
        Basándote en el siguiente SUMMARY del mundo y SCRIPT:
        
        {assets_context}
        
        SUMMARY:
        {state['world_model_summary'][:1500]}
        
        {narrative_context}
        
        SCRIPT (Guión completo con descripción detallada de cada viñeta):
        {batch_script_text}
        
        TAMAÑO DE PÁGINA RECOMENDADO: {state.get('canvas_dimensions', '800x1100 (A4)')}
        ESTILO DE LAYOUT: {state.get('layout_style', 'dynamic')}
        {structure_str}

        {'ESTÁS REGENERANDO ÚNICAMENTE LA PÁGINA ' + str(target_page) if target_page else f'ESTÁS GENERANDO LAS PÁGINAS {comic_page_start} A {comic_page_end} DEL CÓMIC'}
        
        {f'CONTEXTO DEL PANEL ANTERIOR (para mantener continuidad): {previous_panel_context}' if previous_panel_context else ''}
        
        ORDEN DE PRIORIDAD:
        - **DISTRIBUCIÓN**: Genera aproximadamente {panels_for_batch} paneles repartidos entre las páginas {comic_page_start} a {comic_page_end}.
        - **ÍNDICE DE ORDEN (CRÍTICO)**: El campo `order_in_page` DEBE EMPEZAR EN 0 para el primer panel de cada página. (Ej: 0, 1, 2...). No empieces en 1.
        - Los `page_number` DEBEN ir de {comic_page_start} a {comic_page_end}.
        - **CONTINUIDAD**: El primer panel debe ser la continuación inmediata del contexto anterior (si existe).
        
        FORMATO JSON OBLIGATORIO:
        {{
            "panels": [
                {{
                    "page_number": {comic_page_start},
                    "order_in_page": 0,
                    "scene_description": "Descripción detallada de la escena...",
                    "script": "parte del guión que describe detalladamente el panel o viñeta, no solo el diálogo sino la descripción completa de la escena.",
                    "characters": ["Nombre del Personaje"],
                    "scenery": "Lugar donde se desarrolla este panel o viñeta",
                    "style": "Estilo de dibujo"
                }}
            ]
        }}
        
        Responde ÚNICAMENTE con un JSON válido. No incluyas texto fuera del bloque de código JSON.
        """
        
        response = llm.invoke([
            SystemMessage(content="Eres un director de arte de cómics experto en descomposición de guiones. Responde SIEMPRE con un JSON válido."),
            HumanMessage(content=batch_prompt)
        ])
        
        content = response.content.strip()
        print(f"DEBUG: [PLANNER BATCH] Pages {comic_page_start}-{comic_page_end} Output: {content[:200]}...")

        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        
        return json.loads(content)
    
    # ── Execute planning (single or batched) ──
    all_panels = []
    
    try:
        if not use_batching:
            # Single call for short scripts
            batch_text = ""
            for pg in sorted_script_pages:
                batch_text += f"\n\n=== PÁGINA {pg} DEL GUIÓN ===\n{script_pages[pg]}"
            
            comic_page_start = target_page if target_page else 1
            comic_page_end = target_page if target_page else max_pages_comic
            
            narrative_ctx = get_narrative_context_for_pages(sorted_script_pages)
            
            data = plan_batch(
                batch_text, narrative_ctx, comic_page_start, comic_page_end,
                max_panels_comic if max_panels_comic else panels_per_page * max_pages_comic,
                ""
            )
            all_panels = _extract_panels_from_data(data)
        else:
            # Batched processing: map script page batches -> comic page ranges
            previous_context = ""
            
            # Calculate how many comic pages each script batch maps to
            script_to_comic_ratio = max_pages_comic / len(sorted_script_pages) if sorted_script_pages else 1
            
            for batch_idx in range(0, len(sorted_script_pages), BATCH_SIZE):
                batch_page_nums = sorted_script_pages[batch_idx:batch_idx + BATCH_SIZE]
                batch_text = ""
                for pg in batch_page_nums:
                    batch_text += f"\n\n=== PÁGINA {pg} DEL GUIÓN ===\n{script_pages[pg]}"
                
                # Map this batch of script pages to comic page range
                comic_page_start = int(batch_idx * script_to_comic_ratio) + 1
                comic_page_end = min(int((batch_idx + len(batch_page_nums)) * script_to_comic_ratio) + 1, max_pages_comic)
                # Ensure at least 1 page per batch
                if comic_page_end < comic_page_start:
                    comic_page_end = comic_page_start
                
                batch_panels_count = panels_per_page * (comic_page_end - comic_page_start + 1)
                
                print(f"DEBUG: [PLANNER BATCH] Script pages {batch_page_nums[0]}-{batch_page_nums[-1]} -> Comic pages {comic_page_start}-{comic_page_end} ({batch_panels_count} panels)")
                
                narrative_ctx = get_narrative_context_for_pages(batch_page_nums)
                data = plan_batch(batch_text, narrative_ctx, comic_page_start, comic_page_end, batch_panels_count, previous_context)
                batch_panels = _extract_panels_from_data(data)
                
                if batch_panels:
                    # Save last panel as context for next batch
                    last = batch_panels[-1]
                    previous_context = f"Página {last.get('page_number')}, Escena: {last.get('scene_description', '')[:200]}, Personajes: {', '.join(last.get('characters', []))}"
                    all_panels.extend(batch_panels)
                    print(f"DEBUG: [PLANNER BATCH] Got {len(batch_panels)} panels. Total so far: {len(all_panels)}")
        
        if not all_panels:
            raise ValueError("No panels were generated by the LLM from the script.")

        # ── Post-process: normalize IDs, page numbers, layouts ──
        page_counts = {}
        existing_layout_map = {
            (p.get("page_number"), p.get("order_in_page")): p.get("layout") 
            for p in existing_panels 
            if p.get("layout") and p.get("layout").get("w", 0) > 0
        }

        for i, p in enumerate(all_panels):
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

            prev_layout = existing_layout_map.get((p_num, p_order))
            if prev_layout:
                print(f"DEBUG: [PLANNER] Inheriting Layout for Pág {p_num}, Orden {p_order} -> {prev_layout}")
                p["layout"] = prev_layout
            else:
                p.setdefault("layout", {})
            
            if not p.get("prompt"):
                p["prompt"] = "Cinematic comic panel"

        final_panels = preserved_panels + all_panels
        return {"panels": final_panels, "current_step": "layout_designer"}
    except Exception as e:
        print(f"CRITICAL ERROR en planner: {e}")
        import traceback
        traceback.print_exc()
        raise e

def _extract_panels_from_data(data) -> list:
    """Helper: extract panel dicts from an LLM JSON response with flexible structure."""
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
    if not panels and isinstance(data, list):
        panels = data
    return panels

def image_generator(state: AgentState):
    print("--- AGENT F & H: MULTIMODAL IMAGE GENERATION ---")
    adapter = get_image_adapter()
    pb = PromptBuilder(state["project_id"])
    cs = ContinuitySupervisor(state["project_id"])
    
    updated_panels = []
    continuity = state.get("continuity_state", {})
    
    sorted_panels = sorted(state["panels"], key=lambda x: (x.get('page_number', 1), x.get('order_in_page', 0)))
    
    # Identificar personajes y escenarios para contexto multimodal
    cm = pb.cm 
    scm = pb.scm
    
    target_panel_id = str(state.get("panel_id")) if state.get("panel_id") else None

    for panel in sorted_panels:
        # Si es regeneración selectiva, saltar si no es el ID objetivo
        if state.get("action") == "regenerate_panel" and target_panel_id:
            if str(panel.get("id")) != target_panel_id:
                updated_panels.append(panel)
                continue

        is_target = state.get("action") == "regenerate_panel" and str(panel.get("id")) == target_panel_id
        
        if panel.get("image_url") and panel.get("status") not in ["pending", "editing"] and not is_target:
            updated_panels.append(panel)
            continue

        # Agent H: Update continuity based on the action
        continuity = cs.update_state(continuity, panel)
        
        # Agent F: Build Layered Prompt
        augmented_prompt = pb.build_panel_prompt(panel, state["world_model_summary"], continuity)
        
        # Enrich with panel purpose from Story Understanding
        panel_purposes = state.get("panel_purposes", {})
        page_num = panel.get("page_number", 1)
        order = panel.get("order_in_page", 0)
        purpose_key = f"page_{page_num}_panel_{order + 1}"
        panel_purpose = panel_purposes.get(purpose_key, "")
        if panel_purpose:
            augmented_prompt = f"NARRATIVE PURPOSE: {panel_purpose}\n\n{augmented_prompt}"
            print(f"DEBUG: [StoryUnderstanding -> Generator] Panel {panel.get('id')} enriched with purpose: {panel_purpose[:80]}...")
        
        # Image-to-Image support if current_image_url is provided
        current_img = None
        if is_target:
            # If we are regenerating a specific panel, we MUST respect the I2I flag from the backend
            # (current_image_url). If it's None, it means the user unchecked I2I.
            current_img = state.get("current_image_url")
        else:
            # For massive generation, fallback to what's in the panel dict if present
            current_img = panel.get("current_image_url") or panel.get("image_url")
            
        # Coleccionar imágenes de contexto (Personajes del panel + Imagen de Referencia)
        context_images = []
        for char_name in panel.get("characters", []):
            char_refs = cm.get_character_images(char_name)
            if char_refs:
                context_images.extend(char_refs)
        
        # 1b. Escenario reference
        scene_name = panel.get("scenery")
        if scene_name:
            scene_refs = scm.get_scenery_images(scene_name)
            if scene_refs:
                context_images.extend(scene_refs)
        
        # Add reference image context
        # Prioritize top-level reference_image_url for the target panel
        ref_img = None
        if is_target:
            ref_img = state.get("reference_image_url")
        if not ref_img:
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

        # Definir la imagen inicial para el adapter
        init_image = current_img 
        if not is_target:
            # Solo aplicamos fallbacks si NO es una regeneración manual (donde el usuario decide el I2I)
            if not init_image and panel.get("status") == "editing" and panel.get("image_url"):
                init_image = panel.get("image_url")

        if init_image:
            # Usamos edit_image para que el adapter gestione la descarga de la URL antes de procesar
            # Pasamos unique_context para que Gemini (u otros) usen personajes/referencias incluso en I2I
            print(f"DEBUG: I2I/Editing panel {panel['id']} using init_image: {init_image}")
            url = adapter.edit_image(original_image_url=init_image, prompt=augmented_prompt, style_prompt=panel.get('panel_style'), context_images=unique_context)
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
    target_page = state.get("page_number")
    
    for p in state["panels"]:
        p_num = p["page_number"]
        if target_page and int(p_num) != int(target_page):
            continue
        if p_num not in pages: pages[p_num] = []
        pages[p_num].append(p)
        
    merged_results = state.get("merged_pages", [])
    # Filter out the page being regenerated to avoid duplicates
    if target_page:
        merged_results = [m for m in merged_results if int(m["page_number"]) != int(target_page)]
        
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

        user_instr = state.get('instructions', '')
        instr_part = f"\nUSER INSTRUCTIONS: {user_instr}" if user_instr else ""

        # Enrich with page summary from Story Understanding
        page_summaries = state.get("page_summaries", {})
        page_summary = page_summaries.get(int(page_num), page_summaries.get(str(page_num), ""))
        summary_part = f"\nPAGE NARRATIVE CONTEXT: {page_summary}" if page_summary else ""
        if page_summary:
            print(f"DEBUG: [StoryUnderstanding -> Merger] Page {page_num} enriched with summary: {page_summary[:100]}...")

        merge_prompt = f"ORGANIC COMIC PAGE MERGE. \nInstrucciones visuales: {visual_blend_description} {instr_part}{summary_part} \nPágina en el guión: {page_num}\nStyle: {state.get('style_guide', '')}. Professional comic art style."
        
        # CONTINUIDAD: Agregar la página anterior como referencia visual si existe
        merge_context_images = []
        bucket = os.getenv("AWS_STORAGE_BUCKET_NAME")

        if last_page_s3_key:
            prev_s3_uri = f"s3://{bucket}/{last_page_s3_key}"
            print(f"DEBUG: Adding previous page (Pág {int(page_num)-1}) as continuity context: {prev_s3_uri}")
            merge_context_images.append(prev_s3_uri)
        
        try:
            # 2. Generar mezcla orgánica via Image-to-Image (especializado para fusión)
            print(f"DEBUG: [PageMerger] Sending Page {page_num} to provider for organic blend...")
            raw_merged_s3_key = adapter.generate_page_merge(
                merge_prompt,
                style_prompt=state.get('style_guide', ''),
                init_image_path=composite_path, 
                context_images=merge_context_images
            ) 
            
            # Guardamos esta página para que sea referencia de la siguiente
            last_page_s3_key = raw_merged_s3_key
            
            # El usuario indica que el modelo multimodal ya integra los globos, 
            # por lo que no es necesario el paso de 'apply_final_overlays' que los redibujaba.
            # Usamos directamente el resultado de la fusión.
            
            merged_results.append({"page_number": page_num, "image_url": raw_merged_s3_key})
            print(f"DEBUG: [PageMerger] Page {page_num} merge completed. Result S3 Key: {raw_merged_s3_key}")
            
        except Exception as e:
            print(f"ERROR: [PageMerger] Failed to merge Page {page_num}: {e}")
            raise e
            
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
    workflow.add_node("story_understanding", story_understanding)
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

    workflow.add_edge("ingest", "story_understanding")
    workflow.add_edge("story_understanding", "world_model_builder")
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
