import os
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader, TextLoader
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter

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
        """Descarga e ingesta archivos desde S3/URLs"""
        documents = []
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
                elif not os.path.exists(url):
                    # Si no es URL ni existe localmente, posiblemente es un path relativo que debió ser de S3
                    if url.startswith('/'):
                        print(f"ALERTA: Recibido path relativo '{url}'. Verifique la configuración de S3 en el Backend.")
                    else:
                        print(f"Archivo local no encontrado: {url}")
                    continue
                else:
                    local_url = url

                ext = local_url.split('.')[-1].lower()
                if ext == 'pdf':
                    loader = PyPDFLoader(local_url)
                elif ext == 'docx':
                    loader = Docx2txtLoader(local_url)
                else:
                    loader = TextLoader(local_url, encoding='utf-8')
                
                documents.extend(loader.load())
                
                # Opcional: limpiar temporales si se descargaron de S3
                # if url.startswith("s3://") and os.path.exists(local_url):
                #    os.remove(local_url)

            except Exception as e:
                print(f"Error cargando {url}: {e}. Se ignorará este archivo.")

        # Si no hay documentos (caso prototipo/S3 simulado), inyectamos datos por defecto para el RAG
        if not documents:
            from langchain_core.documents import Document
            print("Inyectando datos de mundo por defecto para el prototipo.")
            documents = [
                Document(
                    page_content="""
                    Mundo: Ciudad futurista con estética Noir y luces de neón.
                    Estilo: Dibujo a mano, sombras profundas, alto contraste.
                    Personajes: 
                    - Héroe: Detective con gabardina larga y brazo robótico.
                    - Villano: Inteligencia artificial con avatar holográfico púrpura.
                    """,
                    metadata={"source": "default_mock"}
                )
            ]

        splits = self.text_splitter.split_documents(documents)
        vectorstore = Chroma.from_documents(
            documents=splits,
            embedding=self.embeddings,
            persist_directory=self.persist_directory
        )
        return vectorstore

    def query_world_rules(self, query: str, k: int = 3):
        """Consulta el 'World Model' para consistencia"""
        if not os.path.exists(self.persist_directory):
            return []
        
        vectorstore = Chroma(
            persist_directory=self.persist_directory,
            embedding_function=self.embeddings
        )
        return vectorstore.similarity_search(query, k=k)

class CharacterManager:
    """Gestiona la consistencia de personajes mediante 'Character Bibles'"""
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.base_path = f"./data/projects/{project_id}"
        os.makedirs(self.base_path, exist_ok=True)
        self.file_path = f"{self.base_path}/characters.json"
        self.characters = self._load()

    def _load(self):
        if os.path.exists(self.file_path):
            import json
            with open(self.file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save(self):
        import json
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(self.characters, f, indent=4)

    def register_character(self, name: str, description: str, reference_images: list):
        self.characters[name] = {
            "description": description,
            "ref_images": reference_images, # URLs de S3 con turnarounds
            "traits": [] # Rasgos extraídos automáticamente
        }
        self._save()

    def get_character_prompt_segment(self, name: str):
        if name in self.characters:
            char = self.characters[name]
            return f"Personaje: {name}. Descripción: {char['description']}. Mantener consistencia con rasgos visuales clave."
        return f"Personaje: {name}."
