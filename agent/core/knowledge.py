import os
import json
import base64
from typing import List, Dict, Optional
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader, TextLoader
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.messages import HumanMessage
import unicodedata
import re

def normalize_key(text: str) -> str:
    """Normaliza una cadena para ser usada como key de JSON (sin tildes, ñ, espacios, etc)"""
    # 1. Quitar tildes y caracteres latinos
    text = unicodedata.normalize('NFD', text).encode('ascii', 'ignore').decode('utf-8')
    # 2. Quedarse solo con alfanuméricos y guiones
    text = re.sub(r'[^a-zA-Z0-9\s_-]', '', text)
    # 3. CamelCase o snake_case? El usuario sugirió "HabitacionMarie".
    # Vamos a simplemente quitar espacios y mantener mayúsculas para respetar el estilo existente.
    return "".join(text.split())

class KnowledgeManager:
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.persist_directory = f"./data/chroma/{project_id}"
        self.embeddings = OpenAIEmbeddings()
        self.text_splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=400)

    def _download_from_s3(self, s3_url: str):
        """Descarga un archivo de S3 a un directorio temporal y retorna la ruta local"""
        import boto3
        from urllib.parse import urlparse
        
        parsed = urlparse(s3_url)
        bucket = parsed.netloc
        key = parsed.path.lstrip('/')
        
        s3 = boto3.client(
            "s3",
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            region_name=os.getenv("AWS_REGION")
        )
        
        temp_dir = "./data/temp_downloads"
        os.makedirs(temp_dir, exist_ok=True)
        local_path = os.path.join(temp_dir, os.path.basename(key))
        
        print(f"Downloading {s3_url} to {local_path}...")
        s3.download_file(bucket, key, local_path)
        return local_path

    def ingest_from_urls(self, file_urls: list):
        """Descarga e ingesta archivos desde S3/URLs. Retorna (vectorstore, image_paths)"""
        documents = []
        image_paths = []
        image_extensions = {'.jpg', '.png', '.jpeg', '.webp', '.gif'}

        for url in file_urls:
            try:
                if url.startswith("s3://"):
                    local_url = self._download_from_s3(url)
                elif url.startswith("http"):
                    # Detectar si es una URL de S3
                    if ".s3." in url or ".s3-" in url or "amazonaws.com" in url:
                        from urllib.parse import urlparse
                        parsed = urlparse(url)
                        hostname = parsed.netloc
                        if hostname.endswith(".amazonaws.com"):
                            parts = hostname.split('.')
                            if "s3" in parts:
                                bucket_name = parts[0]
                                key = parsed.path.lstrip('/')
                                s3_uri = f"s3://{bucket_name}/{key}"
                                print(f"DEBUG: Re-routing HTTP S3 to S3 URI for indexing: {s3_uri}")
                                local_url = self._download_from_s3(s3_uri)
                                # Skip natural HTTP download
                                url = "s3_redirected" 

                    if url.startswith("http"):
                        import requests
                        from urllib.parse import urlparse
                        
                        parsed = urlparse(url)
                        filename = os.path.basename(parsed.path) or "downloaded_file"
                        temp_dir = "./data/temp_downloads"
                        os.makedirs(temp_dir, exist_ok=True)
                        local_url = os.path.join(temp_dir, filename)
                        
                        print(f"Downloading HTTP URL: {url} -> {local_url}")
                        r = requests.get(url, stream=True, timeout=30)
                        r.raise_for_status()
                        with open(local_url, 'wb') as f:
                            for chunk in r.iter_content(chunk_size=8192):
                                f.write(chunk)
                else:
                    local_url = url # Local file
                    if not os.path.exists(local_url):
                        print(f"ERROR: Archivo local no encontrado en la ruta: {url}")
                        continue
                
                ext = os.path.splitext(local_url)[1].lower()
                
                if ext in image_extensions:
                    print(f"DEBUG: Found image reference: {local_url}")
                    image_paths.append(local_url)
                    continue

                print(f"DEBUG: Cargando documento con extensión {ext} desde {local_url}")

                if ext == '.pdf':
                    loader = PyPDFLoader(local_url)
                elif ext == '.docx':
                    loader = Docx2txtLoader(local_url)
                else:
                    loader = TextLoader(local_url, encoding='utf-8')
                
                documents.extend(loader.load())

            except Exception as e:
                print(f"WARNING error cargando {url}: {e}")
                continue

        vectorstore = None
        if documents:
            print(f"Ingestados {len(documents)} documentos. Pasando a vectorización.")
            splits = self.text_splitter.split_documents(documents)
            vectorstore = Chroma.from_documents(
                documents=splits,
                embedding=self.embeddings,
                persist_directory=self.persist_directory
            )
        
        return vectorstore, image_paths

    def query_world_rules(self, query: str, k: int = 3):
        """Consulta el 'World Model' para consistencia"""
        if not os.path.exists(self.persist_directory):
            return []
        
        vectorstore = Chroma(
            persist_directory=self.persist_directory,
            embedding_function=self.embeddings
        )
        return vectorstore.similarity_search(query, k=k)

class CanonicalStore:
    """Agent B: Canonical Builder - Maintains the 'Official Truth' of the project in S3."""
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.bucket_name = os.getenv("AWS_STORAGE_BUCKET_NAME")
        self.s3_key = f"projects/{project_id}/canon/canon.json"
        
        import boto3
        self.s3 = boto3.client(
            "s3",
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            region_name=os.getenv("AWS_REGION")
        )
        
        self.data = self._load()

    def _load(self) -> Dict:
        try:
            print(f"Loading canon from S3: s3://{self.bucket_name}/{self.s3_key}")
            response = self.s3.get_object(Bucket=self.bucket_name, Key=self.s3_key)
            data = json.loads(response['Body'].read().decode('utf-8'))
            if "metadata" not in data:
                data["metadata"] = {"original_keys": {}}
            return data
        except self.s3.exceptions.NoSuchKey:
            print("Canon not found in S3, initializing new one.")
            return {
                "characters": {},
                "sceneries": {},
                "style": {},
                "continuity": {},
                "metadata": { "original_keys": {} }
            }
        except Exception as e:
            print(f"Error loading canon from S3: {e}")
            return {
                "characters": {},
                "sceneries": {},
                "style": {},
                "continuity": {},
                "metadata": { "original_keys": {} }
            }

    def save(self):
        try:
            print(f"Saving canon to S3: s3://{self.bucket_name}/{self.s3_key}")
            self.s3.put_object(
                Bucket=self.bucket_name,
                Key=self.s3_key,
                Body=json.dumps(self.data, indent=4, ensure_ascii=False),
                ContentType='application/json; charset=utf-8'
            )
        except Exception as e:
            print(f"Error saving canon to S3: {e}")

    def update_character(self, name: str, info: Dict):
        norm_key = normalize_key(name)
        if "metadata" not in self.data: self.data["metadata"] = {"original_keys": {}}
        self.data["metadata"]["original_keys"][norm_key] = name # Save display name
        
        if norm_key not in self.data["characters"]:
            self.data["characters"][norm_key] = {}
        self.data["characters"][norm_key].update(info)
        self.save()

    def update_style(self, style_info: Dict):
        self.data["style"].update(style_info)
        self.save()

    def update_scenery(self, name: str, info: Dict):
        norm_key = normalize_key(name)
        if "metadata" not in self.data: self.data["metadata"] = {"original_keys": {}}
        self.data["metadata"]["original_keys"][norm_key] = name # Save display name

        if norm_key not in self.data["sceneries"]:
            self.data["sceneries"][norm_key] = {}
        self.data["sceneries"][norm_key].update(info)
        self.save()

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
        
        # Prefer direct vision model (Gemini 2.0 Flash is efficient here)
        llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0)
        
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
            # Build multimodal content with ALL images
            content_parts = [{"type": "text", "text": traits_prompt}]
            
            for image_url in image_urls:
                # Detect extension for MIME type (handling pre-signed URLs with query params)
                base_path = image_url.split('?')[0]
                ext = os.path.splitext(base_path)[1].lower()
                mime_type = "image/jpeg" if ext in ['.jpg', '.jpeg', '.jfif'] else "image/png"
                
                # Download image data
                if image_url.startswith("s3://"):
                    km = KnowledgeManager(self.project_id)
                    local_path = km._download_from_s3(image_url)
                    with open(local_path, "rb") as f:
                        img_data = base64.b64encode(f.read()).decode("utf-8")
                else:
                    import requests
                    print(f"DEBUG: Downloading image from URL: {image_url[:80]}...")
                    r = requests.get(image_url, timeout=30)
                    r.raise_for_status()
                    img_data = base64.b64encode(r.content).decode("utf-8")
                
                print(f"DEBUG: Image downloaded for {name}. Size: {len(img_data)} bytes. Detected MIME: {mime_type}")
                
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{img_data}"},
                })

            message = HumanMessage(content=content_parts)
            
            print(f"DEBUG: Invoking Gemini Vision for {name} with {len(image_urls)} images...")
            response = llm.invoke([message])
            content = response.content.strip()
            print(f"DEBUG: Raw AI Response for {name}: {content}")
            
            # Robust JSON Extract
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
            import traceback
            traceback.print_exc()

    def register_character(self, name: str, description: str, reference_images: list):
        # Preservar rasgos existentes si los hay
        existing = self.canon.data.get("characters", {}).get(name, {})
        existing_traits = existing.get("visual_traits", [])
        
        char_info = {
            "description": description,
            "ref_images": reference_images,
            "visual_traits": existing_traits # Preserve instead of resetting
        }
        self.canon.update_character(name, char_info)
        # Automatic trait extraction if images present and no traits existed
        if reference_images and not existing_traits:
            self.extract_visual_traits(name, reference_images)

    def _find_character(self, name: str) -> tuple[Optional[str], Optional[Dict]]:
        """Busca un personaje por nombre exacto, insensible a mayúsculas o por subcadena."""
        chars = self.canon.data.get("characters", {})
        original_keys = self.canon.data.get("metadata", {}).get("original_keys", {})
        
        # 1. Usar la key normalizada para búsqueda directa
        norm_input = normalize_key(name)
        if norm_input in chars:
            return original_keys.get(norm_input, norm_input), chars[norm_input]
            
        # 2. Búsqueda por el nombre original guardado (case-insensitive)
        for norm_key, display_name in original_keys.items():
            if display_name.lower() == name.lower() and norm_key in chars:
                return display_name, chars[norm_key]
            
        # 3. Substring match en nombres originales
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

class StyleManager:
    """Agent B component for managing visual rules and tokens."""
    def __init__(self, project_id: str, canon: Optional[CanonicalStore] = None):
        self.canon = canon or CanonicalStore(project_id)

    def normalize_style(self, style_guide_text: str):
        if not style_guide_text or len(style_guide_text.strip()) < 10:
            print("DEBUG: Style guide text too short, skipping normalization.")
            return

        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
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
            # Langsmith Observability: Tags and Metadata
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

class SceneryManager:
    """Gestiona la consistencia de escenarios mediante 'Scenery Bibles'"""
    def __init__(self, project_id: str, canon: Optional[CanonicalStore] = None):
        self.project_id = project_id
        self.canon = canon or CanonicalStore(project_id)

    def extract_visual_traits(self, name: str, image_urls: List[str]):
        """Agent B: Vision-based trait extraction from scenario reference images."""
        if not image_urls:
            return
        
        print(f"DEBUG: [SceneryManager] Starting visual trait extraction for scenario '{name}' with {len(image_urls)} images.")
        
        llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0)
        
        image_count_text = f"esta imagen de referencia" if len(image_urls) == 1 else f"estas {len(image_urls)} imágenes de referencia"
        traits_prompt = f"""
        Analiza {image_count_text} del escenario '{name}'.
        Extrae rasgos visuales invariantes y detallados para incluirlos en prompts de generación de imágenes.
        Enfócate en:
        - Arquitectura y estructura (ventanas, techos, materiales).
        - Objetos clave y mobiliario fijo.
        - Texturas predominantes (madera, metal, piedra).
        - Esquema de iluminación habitual (fuentes de luz, sombras).
        - Paleta de colores distintiva del lugar.
        
        Si hay múltiples imágenes, busca los rasgos que se mantienen CONSISTENTES entre todas ellas.
        
        Responde en formato JSON:
        {{"traits": ["paredes de ladrillo visto", "gran ventana circular al fondo", "iluminación neón púrpura", ...]}}
        """
        
        try:
            # Build multimodal content with ALL images
            content_parts = [{"type": "text", "text": traits_prompt}]
            
            for image_url in image_urls:
                base_path = image_url.split('?')[0]
                ext = os.path.splitext(base_path)[1].lower()
                mime_type = "image/jpeg" if ext in ['.jpg', '.jpeg', '.jfif'] else "image/png"
                
                if image_url.startswith("s3://"):
                    km = KnowledgeManager(self.project_id)
                    local_path = km._download_from_s3(image_url)
                    with open(local_path, "rb") as f:
                        img_data = base64.b64encode(f.read()).decode("utf-8")
                else:
                    import requests
                    r = requests.get(image_url, timeout=30)
                    r.raise_for_status()
                    img_data = base64.b64encode(r.content).decode("utf-8")
                
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{img_data}"},
                })
            
            message = HumanMessage(content=content_parts)
            
            print(f"DEBUG: Invoking Gemini Vision for scenery {name} with {len(image_urls)} images...")
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
            self.canon.update_scenery(name, {"visual_traits": traits})
            print(f"SUCCESS: Enhanced traits for scenery {name}: {traits}")
        except Exception as e:
            print(f"ERROR extracting vision traits for scenery {name}: {e}")

    def register_scenery(self, name: str, description: str, reference_images: list):
        # Preservar rasgos existentes si los hay
        existing = self.canon.data.get("sceneries", {}).get(name, {})
        existing_traits = existing.get("visual_traits", [])

        scenery_info = {
            "description": description,
            "ref_images": reference_images,
            "visual_traits": existing_traits # Preserve instead of resetting
        }
        self.canon.update_scenery(name, scenery_info)
        # Automatic trait extraction if images present and no traits existed
        if reference_images and not existing_traits:
            self.extract_visual_traits(name, reference_images)

    def _find_scenery(self, name: str) -> tuple[Optional[str], Optional[Dict]]:
        """Busca un escenario por nombre exacto, insensible a mayúsculas o por subcadena."""
        scenes = self.canon.data.get("sceneries", {})
        original_keys = self.canon.data.get("metadata", {}).get("original_keys", {})

        # 1. Usar la key normalizada
        norm_input = normalize_key(name)
        if norm_input in scenes:
            return original_keys.get(norm_input, norm_input), scenes[norm_input]

        # 2. Case-insensitive exact en nombres originales
        for norm_key, display_name in original_keys.items():
            if display_name.lower() == name.lower() and norm_key in scenes:
                return display_name, scenes[norm_key]
            
        # 3. Substring match en nombres originales
        for norm_key, display_name in original_keys.items():
            if (name.lower() in display_name.lower() or display_name.lower() in name.lower()) and norm_key in scenes:
                return display_name, scenes[norm_key]
        return None, None

    def get_scenery_images(self, name: str) -> List[str]:
        name_found, scenery = self._find_scenery(name)
        if scenery:
            return scenery.get("ref_images", [])
        return []

    def get_scenery_prompt_segment(self, name: str):
        name_found, scenery = self._find_scenery(name)
        if scenery:
            traits = scenery.get("visual_traits", [])
            trait_str = "\n".join([f"    * {t}" for t in traits]) if traits else "    * No se detectaron rasgos específicos."
            display_name = name_found or name
            return f"Escenario: {display_name}\n  - Descripción: {scenery.get('description', '')}\n  - Arquitectura y Detalles del Entorno:\n{trait_str}"
        return f"Escenario: {name} (Sin datos canónicos)"
