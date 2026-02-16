import os
from typing import List, Tuple, Optional
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader, TextLoader
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter

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
                    local_url = url
                    if not os.path.exists(local_url):
                        print(f"ERROR: Archivo local no encontrado en la ruta: {url}")
                        continue
                
                ext = os.path.splitext(local_url)[1].lower()
                
                if ext in image_extensions:
                    image_paths.append(local_url)
                    continue

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
