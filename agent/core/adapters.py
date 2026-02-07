from abc import ABC, abstractmethod
import os
import boto3
from openai import OpenAI

class ImageModelAdapter(ABC):
    @abstractmethod
    def generate_image(self, prompt: str, aspect_ratio: str = "1:1", **kwargs) -> str:
        """Generates an image and returns the URL or S3 path"""
        pass

    @abstractmethod
    def edit_image(self, original_image_url: str, prompt: str, mask_url: str = None) -> str:
        """Edits an existing image (Inpainting/Outpainting)"""
        pass

class OpenAIAdapter(ImageModelAdapter):
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def generate_image(self, prompt: str, aspect_ratio: str = "1:1", **kwargs) -> str:
        # Lógica para DALL-E 3
        response = self.client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            n=1,
            size="1024x1024"
        )
        return response.data[0].url

    def edit_image(self, original_image_url: str, prompt: str, mask_url: str = None) -> str:
        # Lógica para DALL-E edit
        pass

class BedrockTitanAdapter(ImageModelAdapter):
    def __init__(self):
        self.client = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION"))

    def generate_image(self, prompt: str, aspect_ratio: str = "1:1", **kwargs) -> str:
        import json
        import base64
        
        body = json.dumps({
            "taskType": "TEXT_IMAGE",
            "textToImageParams": {
                "text": prompt
            },
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
        
        # En una implementación real, subirías esto a S3 y devolverías la URL.
        # Para el prototipo, devolvemos el data-uri si es pequeño o una ruta simulada.
        return f"data:image/png;base64,{base64_image}"

    def edit_image(self, original_image_url: str, prompt: str, mask_url: str = None) -> str:
        # Implementar Inpainting/Outpainting con Titan
        pass

def get_image_adapter() -> ImageModelAdapter:
    provider = os.getenv("IMAGE_GEN_PROVIDER", "openai").lower()
    if provider == "openai":
        return OpenAIAdapter()
    elif provider == "bedrock":
        return BedrockTitanAdapter()
    raise ValueError(f"Provider {provider} not supported.")
