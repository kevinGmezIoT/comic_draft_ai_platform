import os
import json
import base64
import requests
from typing import List, Dict, Optional
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from .canonical_store import CanonicalStore
from .utils import normalize_key

class CharacterManager:
    """Gestiona la consistencia de personajes mediante 'Character Bibles'"""
    def __init__(self, project_id: str, canon: Optional[CanonicalStore] = None):
        self.project_id = project_id
        self.canon = canon or CanonicalStore(project_id)

    def extract_visual_traits(self, name: str, image_urls: List[str]):
        """Agent B: Vision-based trait extraction from reference images."""
        if not image_urls:
            return
        
        print(f"DEBUG: [CharacterManager] Starting visual trait extraction for '{name}' with {len(image_urls)} images.")
        
        # Prefer direct vision model
        llm = ChatGoogleGenerativeAI(model=os.getenv("GEMINI_MODEL_ID_TEXT"), temperature=0)
        
        image_count_text = f"esta imagen de referencia" if len(image_urls) == 1 else f"estas {len(image_urls)} imágenes de referencia"
        traits_prompt = f"""
        Analiza {image_count_text} del personaje '{name}'.
        Extrae rasgos visuales invariantes y detallados para incluirlos en prompts de generación de imágenes.
        Enfócate en:
        - Peinado y color de cabello (textura).
        - Color de ojos y rasgos faciales (cicatrices, tatuajes, forma).
        - Complexión física.
        - Ropa base o accesorios característicos.
        - Paleta de colores predominante.
        
        Si hay múltiples imágenes, busca los rasgos que se mantienen CONSISTENTES entre todas ellas.
        
        Responde en formato JSON:
        {{"traits": ["pelirrojo con peinado despeinado", "ojo izquierdo plateado", "pequeña cicatriz en mejilla derecha", ...]}}
        """
        
        try:
            content_parts = [{"type": "text", "text": traits_prompt}]
            
            for image_url in image_urls:
                # Robust handling of relative S3 paths (projects/...)
                if not image_url.startswith(("http", "s3://")) and image_url.startswith("projects/"):
                    bucket = os.getenv("AWS_STORAGE_BUCKET_NAME")
                    if bucket:
                        print(f"DEBUG: Fixing relative S3 path: {image_url} -> s3://{bucket}/{image_url}")
                        image_url = f"s3://{bucket}/{image_url}"

                base_path = image_url.split('?')[0]
                ext = os.path.splitext(base_path)[1].lower()
                mime_type = "image/jpeg" if ext in ['.jpg', '.jpeg', '.jfif'] else "image/png"
                
                if image_url.startswith("s3://"):
                    # We need a way to download from S3 here. 
                    # For now, we'll assume KnowledgeManager handles the download or we use a temporary helper.
                    # To avoid circularity, we might want to move _download_from_s3 to a util.
                    from ..knowledge import KnowledgeManager as KM
                    km = KM(self.project_id)
                    local_path = km._download_from_s3(image_url)
                    with open(local_path, "rb") as f:
                        img_data = base64.b64encode(f.read()).decode("utf-8")
                else:
                    print(f"DEBUG: Downloading image from URL: {image_url[:80]}...")
                    r = requests.get(image_url, timeout=30)
                    r.raise_for_status()
                    img_data = base64.b64encode(r.content).decode("utf-8")
                
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{img_data}"},
                })

            message = HumanMessage(content=content_parts)
            
            print(f"DEBUG: Invoking Gemini Vision for {name} with {len(image_urls)} images...")
            response = llm.invoke([message])
            content = response.content.strip()
            
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].strip()
            
            if "{" in content:
                start = content.find("{")
                end = content.rfind("}") + 1
                content = content[start:end]
            
            data = json.loads(content)
            traits = data.get("traits", [])
            self.canon.update_character(name, {"visual_traits": traits})
            print(f"SUCCESS: Enhanced traits for {name}: {traits}")
        except Exception as e:
            print(f"ERROR extracting vision traits for {name}: {e}")

    def register_character(self, name: str, description: str, reference_images: list):
        existing = self.canon.data.get("characters", {}).get(name, {})
        existing_traits = existing.get("visual_traits", [])
        
        char_info = {
            "description": description,
            "ref_images": reference_images,
            "visual_traits": existing_traits
        }
        self.canon.update_character(name, char_info)
        if reference_images and not existing_traits:
            self.extract_visual_traits(name, reference_images)

    def _find_character(self, name: str) -> tuple[Optional[str], Optional[Dict]]:
        chars = self.canon.data.get("characters", {})
        original_keys = self.canon.data.get("metadata", {}).get("original_keys", {})
        
        norm_input = normalize_key(name)
        if norm_input in chars:
            return original_keys.get(norm_input, norm_input), chars[norm_input]
            
        for norm_key, display_name in original_keys.items():
            if display_name.lower() == name.lower() and norm_key in chars:
                return display_name, chars[norm_key]
            
        for norm_key, display_name in original_keys.items():
            if (name.lower() in display_name.lower() or display_name.lower() in name.lower()) and norm_key in chars:
                return display_name, chars[norm_key]
        return None, None

    def get_character_images(self, name: str) -> List[str]:
        name_found, char = self._find_character(name)
        if char:
            return char.get("ref_images", [])
        return []

    def get_character_prompt_segment(self, name: str):
        name_found, char = self._find_character(name)
        if char:
            traits = char.get("visual_traits", [])
            trait_str = "\n".join([f"    * {t}" for t in traits]) if traits else "    * No se detectaron rasgos específicos."
            display_name = name_found or name
            return f"Personaje: {display_name}\n  - Descripción: {char.get('description', '')}\n  - Rasgos Visuales Críticos:\n{trait_str}"
        return f"Personaje: {name} (Sin datos canónicos)"
