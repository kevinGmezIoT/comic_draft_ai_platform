import json
import os
from typing import Optional
from langchain_openai import ChatOpenAI
from .canonical_store import CanonicalStore

class StyleManager:
    """Agent B component for managing visual rules and tokens."""
    def __init__(self, project_id: str, canon: Optional[CanonicalStore] = None):
        self.canon = canon or CanonicalStore(project_id)

    def normalize_style(self, style_guide_text: str):
        if not style_guide_text or len(style_guide_text.strip()) < 10:
            print("DEBUG: Style guide text too short, skipping normalization.")
            return

        llm = ChatOpenAI(model=os.getenv("OPENAI_MODEL_ID"), temperature=0)
        prompt = f"""
        Actúa como un Experto en Estética de Cómics. Convierte esta guía de estilo en un conjunto de TOKENS visuales precisos.
        
        GUÍA DE ESTILO/CONTEXTO: 
        {style_guide_text}
        
        INSTRUCCIONES:
        1. Extrae únicamente descriptores de ESTILO ARTÍSTICO (técnica, líneas, paleta, iluminación, tipo de ilustración).
        2. IGNORA nombres de personajes, tramas o diálogos.
        3. Genera una lista de 5-10 tokens en inglés (ej: 'thick noir lines', 'pastel palette', 'watercolor textures').
        
        Responde ÚNICAMENTE en JSON:
        {{"style_tokens": ["...", "..."]}}
        """
        try:
            res = llm.invoke(
                prompt, 
                config={
                    "tags": ["style-normalization", self.canon.project_id],
                    "metadata": {"project_id": self.canon.project_id}
                }
            )
            content = res.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            data = json.loads(content)
            data["style_tokens"].append(style_guide_text)
            self.canon.update_style(data)
            print(f"SUCCESS: Normalized style tokens: {data.get('style_tokens')}")
        except Exception as e:
            print(f"Error normalizing style: {e}")

    def get_style_prompt(self):
        tokens = self.canon.data["style"].get("style_tokens", [])
        if tokens:
            return f"Art Style: {', '.join(tokens)}. Organic comic book aesthetic."
        return "Professional comic book art style."
