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
        self.text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)

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
                    import requests
                    from urllib.parse import urlparse
                    
                    parsed = urlparse(url)
                    filename = os.path.basename(parsed.path) or "downloaded_file"
                    temp_dir = "./data/temp_downloads"
                    os.makedirs(temp_dir, exist_ok=True)
                    local_url = os.path.join(temp_dir, filename)
                    
                    print(f"Downloading HTTP URL: {url} -> {local_url}")
                    r = requests.get(url, stream=True)
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
        
        # Prefer direct vision model (Gemini 1.5 Flash is efficient here)
        llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0)
        
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
        # A more robust version would batch/summarize multiples
        image_url = image_urls[0]
        
        try:
            # Download image data if it's an S3 url
            km = KnowledgeManager(self.project_id)
            if image_url.startswith("s3://"):
                local_path = km._download_from_s3(image_url)
                with open(local_path, "rb") as f:
                    img_data = base64.b64encode(f.read()).decode("utf-8")
            else:
                import requests
                img_data = base64.b64encode(requests.get(image_url).content).decode("utf-8")

            message = HumanMessage(
                content=[
                    {"type": "text", "text": traits_prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{img_data}"},
                    },
                ]
            )
            
            response = llm.invoke([message])
            content = response.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            
            data = json.loads(content)
            self.canon.update_character(name, {"visual_traits": data.get("traits", [])})
            print(f"Enhanced traits for {name}: {data.get('traits')}")
        except Exception as e:
            print(f"Error extracting vision traits for {name}: {e}")

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
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        prompt = f"""
        Convierte esta guía de estilo de cómic en un conjunto de TOKENS visuales precisos para difusión estable / DALL-E.
        GUÍA: {style_guide_text}
        
        Genera una lista de 5-10 descriptores clave (ej: 'thick noir lines', 'pastel palette', 'watercolor textures').
        Responde en JSON:
        {{"style_tokens": ["...", "..."]}}
        """
        try:
            res = llm.invoke(prompt)
            data = json.loads(res.content.replace("```json", "").replace("```", ""))
            self.canon.update_style(data)
        except Exception as e:
            print(f"Error normalizing style: {e}")

    def get_style_prompt(self):
        tokens = self.canon.data["style"].get("style_tokens", [])
        if tokens:
            return f"Art Style: {', '.join(tokens)}. Organic comic book aesthetic."
        return "Professional comic book art style."
