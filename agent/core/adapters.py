from abc import ABC, abstractmethod
import os
import boto3
from openai import OpenAI

class ImageModelAdapter(ABC):
    @abstractmethod
    def generate_image(self, prompt: str, aspect_ratio: str = "1:1", init_image_path: str = None, **kwargs) -> str:
        """Generates an image and returns the URL or S3 path. init_image_path used for i2i."""
        pass

    def edit_image(self, original_image_url: str, prompt: str, mask_url: str = None) -> str:
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
                s3.download_fileobj(bucket, original_image_url, tmp_path)
        
            # 2. Llamar a la implementación específica de cada modelo pasando el path local
            return self.generate_image(prompt, init_image_path=tmp_path)
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

    def generate_image(self, prompt: str, aspect_ratio: str = "1:1", init_image_path: str = None, **kwargs) -> str:
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

    def edit_image(self, original_image_url: str, prompt: str, mask_url: str = None) -> str:
        return super().edit_image(original_image_url, prompt, mask_url)

class BedrockTitanAdapter(ImageModelAdapter):
    def __init__(self):
        self.client = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION"))

    def generate_image(self, prompt: str, aspect_ratio: str = "1:1", init_image_path: str = None, **kwargs) -> str:
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

    def edit_image(self, original_image_url: str, prompt: str, mask_url: str = None) -> str:
        return super().edit_image(original_image_url, prompt, mask_url)

class GoogleGeminiAdapter(ImageModelAdapter):
    def __init__(self):
        from google import genai
        self.api_key = os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY not found in environment.")
        self.client = genai.Client(api_key=self.api_key)
        # Modelo verificado por el usuario
        self.model_id = "gemini-2.5-flash-image"

    def generate_image(self, prompt: str, aspect_ratio: str = "1:1", init_image_path: str = None, **kwargs) -> str:
        from google.genai import types
        import PIL.Image
        
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
            contents = [prompt]
            if init_image_path:
                print(f"DEBUG: Multi-modal Image Variation (i2i) with {self.model_id}...")
                img = PIL.Image.open(init_image_path)
                contents.append(img)
            else:
                print(f"DEBUG: Multi-modal Text-to-Image with {self.model_id}...")

            # Para Gemini multimodal con salida de imagen:
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE"],
                    image_config=types.ImageConfig(
                        aspect_ratio=target_ar
                    )
                )
            )

            image_bytes = None
            for part in response.parts:
                if part.inline_data:
                    image_bytes = part.inline_data.data
                    break
            
            if not image_bytes:
                # Algunos SDKs pueden devolver la imagen de forma distinta en response.candidates
                if hasattr(response, 'candidates') and response.candidates:
                    for part in response.candidates[0].content.parts:
                        if part.inline_data:
                            image_bytes = part.inline_data.data
                            break

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
