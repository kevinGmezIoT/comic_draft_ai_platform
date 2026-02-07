from abc import ABC, abstractmethod
import os
import boto3
from openai import OpenAI

class ImageModelAdapter(ABC):
    @abstractmethod
    def generate_image(self, prompt: str, aspect_ratio: str = "1:1", init_image_path: str = None, **kwargs) -> str:
        """Generates an image and returns the URL or S3 path. init_image_path used for i2i."""
        pass

    @abstractmethod
    def edit_image(self, original_image_url: str, prompt: str, mask_url: str = None) -> str:
        """Edits an existing image (Inpainting/Outpainting)"""
        pass

class OpenAIAdapter(ImageModelAdapter):
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def generate_image(self, prompt: str, aspect_ratio: str = "1:1", init_image_path: str = None, **kwargs) -> str:
        if init_image_path:
            # DALL-E 2 soporta variaciones, DALL-E 3 no directamente vía API clásica de variaciones.
            # Para propósitos de este prototipo, si hay init_image usamos el endpoint de variaciones (v2)
            # O edit si es más apropiado.
            with open(init_image_path, "rb") as image_file:
                response = self.client.images.create_variation(
                    image=image_file,
                    n=1,
                    size="1024x1024"
                )
            return response.data[0].url
        
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
                    "similarityScore": 0.7 # Balance entre original y libertad creativa
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
