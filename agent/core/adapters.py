from abc import ABC, abstractmethod
import os
import boto3
from openai import OpenAI

class ImageModelAdapter(ABC):
    @abstractmethod
    def generate_image(self, prompt: str, style_prompt:str, aspect_ratio: str = "1:1", init_image_path: str = None, context_images: list = None, **kwargs) -> str:
        """Generates an image and returns the URL or S3 path. 
        init_image_path: used for image-to-image variations.
        context_images: list of URLs or S3 paths to use as multimodal context (Gemini)."""
        pass

    def generate_panel(self, prompt: str, style_prompt:str, aspect_ratio: str = "1:1", context_images: list = None, **kwargs) -> str:
        """Especializado para generación de viñetas individuales."""
        return self.generate_image(prompt, style_prompt=style_prompt, aspect_ratio=aspect_ratio, context_images=context_images, **kwargs)

    def generate_page_merge(self, prompt: str, style_prompt:str, init_image_path: str = None, context_images: list = None, **kwargs) -> str:
        """Especializado para la unión orgánica de páginas."""
        return self.generate_image(prompt, style_prompt=style_prompt, init_image_path=init_image_path, context_images=context_images, **kwargs)

    def edit_image(self, original_image_url: str, prompt: str, style_prompt:str, mask_url: str = None, context_images: list = None) -> str:
        """Edits an existing image (Inpainting/Outpainting/Variation)"""
        import tempfile
        import boto3
        import requests
        
        # 1. Obtener la imagen original (URL o S3 Key)
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
        tmp_path = tmp.name
        tmp.close() # Cierra el handle para Windows
        
        try:
            if original_image_url.startswith('http'):
                r = requests.get(original_image_url)
                with open(tmp_path, "wb") as f:
                    f.write(r.content)
            else:
                s3 = boto3.client("s3")
                bucket = os.getenv("AWS_STORAGE_BUCKET_NAME")
                s3.download_file(bucket, original_image_url, tmp_path)
        
            # 2. Llamar a la implementación específica de cada modelo pasando el path local y contexto
            return self.generate_image(prompt, style_prompt=style_prompt, init_image_path=tmp_path, context_images=context_images)
        finally:
            if os.path.exists(tmp_path):
                try: os.remove(tmp_path)
                except: pass

    def _upload_to_s3(self, image_data: bytes, extension: str = "png") -> str:
        """Sube bytes a S3 y retorna la clave (o URL)"""
        import uuid
        import boto3
        
        s3 = boto3.client(
            "s3",
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            region_name=os.getenv("AWS_REGION")
        )
        bucket = os.getenv("AWS_STORAGE_BUCKET_NAME")
        key = f"generated/{uuid.uuid4()}.{extension}"
        
        s3.put_object(Bucket=bucket, Key=key, Body=image_data, ContentType=f"image/{extension}")
        # Retornamos la clave o URL según conveniencia. El backend espera algo que pueda guardar en ImageField.
        # En AWS S3 con django-storages, guardar la 'key' suele ser suficiente si el bucket es el mismo.
        return key

class OpenAIAdapter(ImageModelAdapter):
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def generate_image(self, prompt: str, style_prompt: str = "", aspect_ratio: str = "1:1", init_image_path: str = None, context_images: list = None, **kwargs) -> str:
        import requests
        
        # Mapear aspect ratio a dimensiones de DALL-E 3
        size = "1024x1024"
        if aspect_ratio == "16:9":
            size = "1792x1024"
        elif aspect_ratio == "9:16":
            size = "1024x1792"

        if init_image_path:
            # Variations always 1024x1024 in OpenAI API currently
            with open(init_image_path, "rb") as image_file:
                response = self.client.images.create_variation(
                    image=image_file,
                    n=1,
                    size="1024x1024"
                )
            url = response.data[0].url
        else:
            response = self.client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                n=1,
                size=size,
                quality="hd" # Forzamos HD para mejores resultados multimodales
            )
            url = response.data[0].url
        
        # Descargar y subir a S3 para persistencia
        img_data = requests.get(url).content
        return self._upload_to_s3(img_data)

    def edit_image(self, original_image_url: str, prompt: str, style_prompt: str = "", mask_url: str = None, context_images: list = None) -> str:
        return super().edit_image(original_image_url, prompt, style_prompt, mask_url, context_images=context_images)

class BedrockTitanAdapter(ImageModelAdapter):
    def __init__(self):
        self.client = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION"))

    def generate_image(self, prompt: str, style_prompt: str = "", aspect_ratio: str = "1:1", init_image_path: str = None, context_images: list = None, **kwargs) -> str:
        import json
        import base64
        
        task_type = "TEXT_IMAGE"
        image_params = {"text": prompt}
        
        if init_image_path:
            task_type = "IMAGE_VARIATION"
            with open(init_image_path, "rb") as f:
                img_base64 = base64.b64encode(f.read()).decode("utf-8")
                image_params = {
                    "text": prompt,
                    "conditionImage": img_base64,
                    "similarityScore": 0.7
                }

        body = json.dumps({
            "taskType": task_type,
            "textToImageParams": image_params if task_type == "TEXT_IMAGE" else None,
            "imageVariationParams": image_params if task_type == "IMAGE_VARIATION" else None,
            "imageGenerationConfig": {
                "numberOfImages": 1,
                "height": 1024,
                "width": 1024,
                "cfgScale": 8.0,
                "seed": 0
            }
        })

        response = self.client.invoke_model(
            body=body,
            modelId="amazon.titan-image-generator-v1",
            accept="application/json",
            contentType="application/json"
        )

        response_body = json.loads(response.get("body").read())
        base64_image = response_body.get("images")[0]
        image_bytes = base64.b64decode(base64_image)
        
        return self._upload_to_s3(image_bytes)

    def edit_image(self, original_image_url: str, prompt: str, style_prompt: str = "", mask_url: str = None, context_images: list = None) -> str:
        return super().edit_image(original_image_url, prompt, style_prompt, mask_url, context_images=context_images)

class GoogleGeminiAdapter(ImageModelAdapter):
    def __init__(self):
        from langchain_google_genai import ChatGoogleGenerativeAI
        
        self.api_key = os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY not found in environment.")
        
        # Initialize LangChain model for traceability
        # We use a lower temperature for consistent results
        self.model_id = "gemini-2.5-flash-image"
        self.llm = ChatGoogleGenerativeAI(
            model=self.model_id,
            google_api_key=self.api_key,
            temperature=0.2
        )

    def generate_panel(self, prompt: str, style_prompt: str = "", aspect_ratio: str = "1:1", context_images: list = None, **kwargs) -> str:
        """Implementación específica de Gemini con contexto de personajes."""
        enriched_prompt = prompt + "\nCharacter(s) reference in image(s) attached."
        return self.generate_image(enriched_prompt, style_prompt=style_prompt, aspect_ratio=aspect_ratio, context_images=context_images, **kwargs)

    def generate_page_merge(self, prompt: str, style_prompt:str, init_image_path: str = None, context_images: list = None, **kwargs) -> str:
        """Implementación específica de Gemini con contexto de página anterior."""
        enriched_prompt = prompt + "\nPrevious page reference in image(s) attached."
        return self.generate_image(enriched_prompt, style_prompt=style_prompt, init_image_path=init_image_path, context_images=context_images, **kwargs)

    def generate_image(self, prompt: str, style_prompt: str = "", aspect_ratio: str = "1:1", init_image_path: str = None, context_images: list = None, **kwargs) -> str:
        from langchain_core.messages import HumanMessage
        from langchain_google_genai import Modality
        import PIL.Image
        import requests
        import base64
        import io
        import tempfile
        
        # Mapear aspect ratio según soporte de Imagen 3 / Gemini Image
        ar_map = {
            "1:1": "1:1",
            "16:9": "16:9",
            "9:16": "9:16",
            "3:4": "3:4",
            "4:3": "4:3"
        }
        target_ar = ar_map.get(aspect_ratio, "1:1")

        try:
            message_content = []
            
            # 1. Agregar imágenes de contexto (personajes, escenas + imagen base para I2I)
            all_input_images = (context_images or []).copy()
            if init_image_path and init_image_path not in all_input_images:
                print(f"DEBUG: Adding init_image_path to Gemini context: {init_image_path}")
                all_input_images.append(init_image_path)

            if all_input_images:
                print(f"DEBUG: Adding {len(all_input_images)} input images to Gemini generation...")
                for img_url in all_input_images:
                    try:
                        img_bytes = None
                        if not img_url: continue

                        if img_url.startswith('http'):
                            # Detectar si es una URL de S3 (para evitar errores 403 por prefirmado expirado)
                            if ".s3." in img_url or ".s3-" in img_url or "amazonaws.com" in img_url:
                                print(f"DEBUG: S3 URL detected in HTTP context: {img_url}")
                                from urllib.parse import urlparse
                                parsed = urlparse(img_url)
                                # Formato virtual host: bucket.s3.amazonaws.com
                                # Formato path: s3.amazonaws.com/bucket/key
                                hostname = parsed.netloc
                                if hostname.endswith(".amazonaws.com"):
                                    parts = hostname.split('.')
                                    if "s3" in parts:
                                        # Es S3. Si el bucket está en el hostname (virtual host)
                                        # bucket.s3.amazonaws.com o bucket.s3-region.amazonaws.com
                                        bucket_name = parts[0]
                                        key = parsed.path.lstrip('/')
                                        # Re-encaminar al bloque de S3
                                        img_url = f"s3://{bucket_name}/{key}"
                                        print(f"DEBUG: Re-routed HTTP S3 URL to S3 URI: {img_url}")
                            
                        # El bloque de S3 ahora manejará tanto s3:// como las re-encaminadas
                        if img_url.startswith('http'):
                            print(f"DEBUG: Downloading image from URL: {img_url}")
                            r = requests.get(img_url, timeout=15)
                            r.raise_for_status()
                            img_bytes = r.content
                        elif img_url.startswith('s3://') or ("/" in img_url and not os.path.exists(img_url)):
                            # Si no existe localmente y parece una ruta de S3 o key, intentar S3
                            s3_uri = img_url
                            if not img_url.startswith('s3://'):
                                bucket = os.getenv("AWS_STORAGE_BUCKET_NAME")
                                s3_uri = f"s3://{bucket}/{img_url}"
                            
                            print(f"DEBUG: Resolving via S3: {s3_uri}")
                            import boto3
                            from urllib.parse import urlparse
                            parsed = urlparse(s3_uri)
                            bucket_name = parsed.netloc
                            key = parsed.path.lstrip('/')
                            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                                tmp_path = tmp.name
                            s3 = boto3.client("s3")
                            s3.download_file(bucket_name, key, tmp_path)
                            with open(tmp_path, 'rb') as f:
                                img_bytes = f.read()
                            os.remove(tmp_path)
                            print(f"DEBUG: Successfully downloaded {len(img_bytes)} bytes from S3.")
                        else:
                            print(f"DEBUG: Reading local image: {img_url}")
                            # Fallback to absolute media path if relative fails
                            actual_path = img_url
                            if not os.path.isabs(img_url) and not os.path.exists(img_url):
                                media_root = os.getenv("MEDIA_ROOT", "./media")
                                actual_path = os.path.join(media_root, img_url)
                            
                            with open(actual_path, 'rb') as f:
                                img_bytes = f.read()
                        
                        if not img_bytes:
                            raise ValueError(f"No bytes retrieved for {img_url}")

                        # Normalizar imagen con PIL para evitar errores de Gemini
                        # Gemini Image Generation puede fallar con imágenes > 1024 o formatos extraños (RGBA, etc)
                        img = PIL.Image.open(io.BytesIO(img_bytes))
                        
                        # Convertir a RGB (elimina transparencias que pueden dar error)
                        if img.mode != 'RGB':
                            img = img.convert('RGB')
                        
                        # Redimensionar si es muy grande (Gemini Image suele tener límites)
                        max_size = 1024
                        if max(img.size) > max_size:
                            ratio = max_size / max(img.size)
                            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
                            img = img.resize(new_size, PIL.Image.LANCZOS)
                            print(f"DEBUG: Resized image from {img_url} to {new_size}")

                        # Volver a bytes
                        output = io.BytesIO()
                        img.save(output, format="JPEG", quality=90)
                        normalized_bytes = output.getvalue()
                        
                        # Determinar MIME type para el Data URL
                        mime_type = "image/jpeg"
                        
                        # LangChain multimodal format
                        img_base64 = base64.b64encode(normalized_bytes).decode("utf-8")
                        message_content.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{img_base64}"}
                        })
                    except Exception as e:
                        print(f"WARNING: Failed to load/normalize context image {img_url}: {e}")

            # 2. Agregar prompt de texto
            message_content.append({"type": "text", "text": prompt})

            # 3. Agregar prompt de estilo
            if style_prompt:
                message_content.append({"type": "text", "text": "\nESTILO: " + style_prompt})

            # 4. Invoke model via LangChain for full traceability
            # IMPORTANT: response_modalities must be a list of Enums, not strings.
            response = self.llm.invoke(
                [HumanMessage(content=message_content)],
                response_modalities=[Modality.IMAGE],
                image_config={"aspect_ratio": target_ar}
            )

            # 5. Extract image from response
            image_bytes = None
            
            # LangChain for Gemini returns image data either in content (list of dicts)
            # or in response_metadata depending on version.
            if isinstance(response.content, list):
                for part in response.content:
                    if isinstance(part, dict) and part.get("type") == "image_url":
                        # Some versions return it here
                        data_url = part["image_url"]["url"]
                        if ";base64," in data_url:
                            image_bytes = base64.b64decode(data_url.split(";base64,")[1])
                            break
            
            # Fallback to response_metadata or raw parts if available in later versions
            if not image_bytes and hasattr(response, 'additional_kwargs'):
                # Handle potential raw parts if LangChain passes them through
                pass

            if not image_bytes:
                # Some implementations might put the binary in response.content directly if it's a single part
                if isinstance(response.content, bytes):
                    image_bytes = response.content
            
            # Robust check for modern LangChain Gemini response format
            if not image_bytes and response.content:
                print(f"DEBUG: Response content type: {type(response.content)}")
                # If it's a string, it might be an error or unexpected text
            
            if not image_bytes:
                raise ValueError(f"No image data found in Gemini response. Response: {response}")

            return self._upload_to_s3(image_bytes)

        except Exception as e:
            print(f"ERROR in GoogleGeminiAdapter: {e}")
            raise e

def get_image_adapter() -> ImageModelAdapter:
    provider = os.getenv("IMAGE_GEN_PROVIDER", "openai").lower()
    if provider == "openai":
        return OpenAIAdapter()
    elif provider == "bedrock":
        return BedrockTitanAdapter()
    elif provider == "gemini":
        return GoogleGeminiAdapter()
    raise ValueError(f"Provider {provider} not supported.")
