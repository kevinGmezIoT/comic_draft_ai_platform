import os
import json
from typing import Dict
from langchain_openai import ChatOpenAI
from .knowledge import CanonicalStore
from .models import Panel

class ContinuitySupervisor:
    """Agent H: Continuity Supervisor - Tracks and validates state between panels."""
    def __init__(self, project_id: str):
        self.canon = CanonicalStore(project_id)
        
    def update_state(self, current_state: Dict, panel: Panel) -> Dict:
        # Simple LLM logic to update state based on panel action
        llm = ChatOpenAI(model=os.getenv("OPENAI_MODEL_ID"), temperature=0)
        
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
