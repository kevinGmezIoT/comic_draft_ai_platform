import hashlib
import os
from typing import List, Tuple, Optional
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader, TextLoader
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from ..telemetry import timed_function, timed_step

class KnowledgeManager:
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.persist_directory = f"./data/chroma/{project_id}"
        self.embeddings = OpenAIEmbeddings()
        self.text_splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=400)
        self.temp_directory = "./data/temp_downloads"

    def _build_cached_path(self, source_id: str, filename: str) -> str:
        os.makedirs(self.temp_directory, exist_ok=True)
        digest = hashlib.sha1(source_id.encode("utf-8")).hexdigest()[:12]
        safe_name = os.path.basename(filename) or "downloaded_file"
        return os.path.join(self.temp_directory, f"{digest}_{safe_name}")

    @timed_function("knowledge.download_s3")
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
        
        local_path = self._build_cached_path(s3_url, key)
        if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
            print(f"DEBUG: Reusing cached S3 download: {local_path}")
            return local_path
        
        print(f"Downloading {s3_url} to {local_path}...")
        s3.download_file(bucket, key, local_path)
        return local_path

    @timed_function("knowledge.download_http")
    def _download_from_http(self, url: str):
        import requests
        from urllib.parse import urlparse

        parsed = urlparse(url)
        filename = os.path.basename(parsed.path) or "downloaded_file"
        local_path = self._build_cached_path(url, filename)
        if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
            print(f"DEBUG: Reusing cached HTTP download: {local_path}")
            return local_path

        print(f"Downloading HTTP URL: {url} -> {local_path}")
        r = requests.get(url, stream=True, timeout=30)
        r.raise_for_status()
        with open(local_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        return local_path

    @timed_function("knowledge.resolve_source")
    def resolve_to_local_path(self, url: str):
        from urllib.parse import urlparse

        if url.startswith("s3://"):
            return self._download_from_s3(url)

        if url.startswith("http"):
            if ".s3." in url or ".s3-" in url or "amazonaws.com" in url:
                parsed = urlparse(url)
                hostname = parsed.netloc
                if hostname.endswith(".amazonaws.com"):
                    parts = hostname.split(".")
                    if "s3" in parts:
                        bucket_name = parts[0]
                        key = parsed.path.lstrip("/")
                        s3_uri = f"s3://{bucket_name}/{key}"
                        print(f"DEBUG: Re-routing HTTP S3 to S3 URI for download: {s3_uri}")
                        return self._download_from_s3(s3_uri)
            return self._download_from_http(url)

        if not os.path.exists(url):
            raise FileNotFoundError(f"Archivo local no encontrado en la ruta: {url}")
        return url

    @timed_function("knowledge.ingest_from_urls")
    def ingest_from_urls(self, file_urls: list):
        """Descarga e ingesta archivos desde S3/URLs. Retorna (vectorstore, image_paths)"""
        documents = []
        image_paths = []
        image_extensions = {'.jpg', '.png', '.jpeg', '.webp', '.gif'}

        for url in file_urls:
            try:
                local_url = self.resolve_to_local_path(url)
                
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
            with timed_step("knowledge.split_documents"):
                splits = self.text_splitter.split_documents(documents)
            with timed_step("knowledge.build_vectorstore"):
                vectorstore = Chroma.from_documents(
                    documents=splits,
                    embedding=self.embeddings,
                    persist_directory=self.persist_directory
                )
        
        return vectorstore, image_paths

    @timed_function("knowledge.query_world_rules")
    def query_world_rules(self, query: str, k: int = 3):
        """Consulta el 'World Model' para consistencia"""
        if not os.path.exists(self.persist_directory):
            return []
        
        vectorstore = Chroma(
            persist_directory=self.persist_directory,
            embedding_function=self.embeddings
        )
        return vectorstore.similarity_search(query, k=k)
