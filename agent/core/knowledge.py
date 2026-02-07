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

    def ingest_from_urls(self, file_urls: list):
        """Descarga e ingesta archivos desde S3/URLs"""
        documents = []
        for url in file_urls:
            try:
                # Si es una ruta simulada de S3 o archivo inexistente, evitamos la carga física
                if url.startswith("s3://") or not os.path.exists(url):
                    print(f"Simulando o saltando ingesta física de: {url}")
                    continue

                ext = url.split('.')[-1].lower()
                if ext == 'pdf':
                    loader = PyPDFLoader(url)
                elif ext == 'docx':
                    loader = Docx2txtLoader(url)
                else:
                    loader = TextLoader(url)
                
                documents.extend(loader.load())
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
