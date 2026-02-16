import os
from typing import Dict, List
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from .knowledge import CharacterManager, StyleManager, SceneryManager, CanonicalStore
from .models import Panel

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

        llm = ChatOpenAI(model=os.getenv("OPENAI_MODEL_ID"), temperature=0.2)
        
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