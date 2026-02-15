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
            return json.loads(response['Body'].read().decode('utf-8'))
        except self.s3.exceptions.NoSuchKey:
            print("Canon not found in S3, initializing new one.")
            return {
                "characters": {},
                "sceneries": {},
                "style": {},
                "continuity": {}
            }
        except Exception as e:
            print(f"Error loading canon from S3: {e}")
            return {
                "characters": {},
                "sceneries": {},
                "style": {},
                "continuity": {}
            }

    def save(self):
        try:
            print(f"Saving canon to S3: s3://{self.bucket_name}/{self.s3_key}")
            self.s3.put_object(
                Bucket=self.bucket_name,
                Key=self.s3_key,
                Body=json.dumps(self.data, indent=4),
                ContentType='application/json'
            )
        except Exception as e:
            print(f"Error saving canon to S3: {e}")

    def update_character(self, name: str, info: Dict):
        if name not in self.data["characters"]:
            self.data["characters"][name] = {}
        self.data["characters"][name].update(info)
        self.save()

    def update_style(self, style_info: Dict):
        self.data["style"].update(style_info)
        self.save()

class CharacterManager:
    """Gestiona la consistencia de personajes mediante 'Character Bibles'"""
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.canon = CanonicalStore(project_id)

    def extract_visual_traits(self, name: str, image_urls: List[str]):
        """Agent B: Vision-based trait extraction from reference images."""
        if not image_urls:
            return
        
        print(f"DEBUG: [CharacterManager] Starting visual trait extraction for '{name}' with {len(image_urls)} images.")
        
        # Prefer direct vision model (Gemini 1.5 Flash is efficient here)
        llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0)
        
        traits_prompt = f"""
        Analiza estas imágenes de referencia del personaje '{name}'.
        Extrae rasgos visuales invariantes y detallados para incluirlos en prompts de generación de imágenes.
        Enfócate en:
        - Peinado y color de cabello (textura).
        - Color de ojos y rasgos faciales (cicatrices, tatuajes, forma).
        - Complexión física.
        - Ropa base o accesorios característicos.
        - Paleta de colores predominante.
        
        Responde en formato JSON:
        {{"traits": ["pelirrojo con peinado despeinado", "ojo izquierdo plateado", "pequeña cicatriz en mejilla derecha", ...]}}
        """
        
        # For now, let's assume we can get one image to analyze
        image_url = image_urls[0]
        
        # Detect extension for MIME type (handling pre-signed URLs with query params)
        base_path = image_url.split('?')[0]
        ext = os.path.splitext(base_path)[1].lower()
        mime_type = "image/jpeg" if ext in ['.jpg', '.jpeg', '.jfif'] else "image/png"
        
        try:
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

            message = HumanMessage(
                content=[
                    {"type": "text", "text": traits_prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{img_data}"},
                    },
                ]
            )
            
            print(f"DEBUG: Invoking Gemini Vision for {name}...")
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
        char_info = {
            "description": description,
            "ref_images": reference_images,
            "visual_traits": [] # To be filled by vision
        }
        self.canon.update_character(name, char_info)
        # Automatic trait extraction if images present
        if reference_images:
            self.extract_visual_traits(name, reference_images)

    def get_character_images(self, name: str) -> List[str]:
        char = self.canon.data["characters"].get(name)
        if char:
            return char.get("ref_images", [])
        return []

    def get_character_prompt_segment(self, name: str):
        char = self.canon.data["characters"].get(name)
        if char:
            traits = ", ".join(char.get("visual_traits", []))
            trait_str = f" Rasgos visuales: {traits}." if traits else ""
            return f"Personaje: {name}. {char['description']}.{trait_str} Mantener rigurosa consistencia con estos rasgos."
        return f"Personaje: {name}."

class StyleManager:
    """Agent B component for managing visual rules and tokens."""
    def __init__(self, project_id: str):
        self.canon = CanonicalStore(project_id)

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
        1. Extrae únicamente descriptores de ESTILO ARTÍSTICO (técnica, líneas, paleta, iluminación).
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
            self.canon.update_style(data)
            print(f"SUCCESS: Normalized style tokens: {data.get('style_tokens')}")
        except Exception as e:
            print(f"Error normalizing style: {e}")

    def get_style_prompt(self):
        tokens = self.canon.data["style"].get("style_tokens", [])
        if tokens:
            return f"Art Style: {', '.join(tokens)}. Organic comic book aesthetic."
        return "Professional comic book art style."
