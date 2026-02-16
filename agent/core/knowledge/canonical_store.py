import os
import json
import boto3
from typing import Dict
from .utils import normalize_key

class CanonicalStore:
    """Agent B: Canonical Builder - Maintains the 'Official Truth' of the project in S3."""
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.bucket_name = os.getenv("AWS_STORAGE_BUCKET_NAME")
        self.s3_key = f"projects/{project_id}/canon/canon.json"
        
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
            data = json.loads(response['Body'].read().decode('utf-8'))
            if "metadata" not in data:
                data["metadata"] = {"original_keys": {}}
            return data
        except self.s3.exceptions.NoSuchKey:
            print("Canon not found in S3, initializing new one.")
            return {
                "characters": {},
                "sceneries": {},
                "style": {},
                "continuity": {},
                "metadata": { "original_keys": {} }
            }
        except Exception as e:
            print(f"Error loading canon from S3: {e}")
            return {
                "characters": {},
                "sceneries": {},
                "style": {},
                "continuity": {},
                "metadata": { "original_keys": {} }
            }

    def save(self):
        try:
            print(f"Saving canon to S3: s3://{self.bucket_name}/{self.s3_key}")
            self.s3.put_object(
                Bucket=self.bucket_name,
                Key=self.s3_key,
                Body=json.dumps(self.data, indent=4, ensure_ascii=False),
                ContentType='application/json; charset=utf-8'
            )
        except Exception as e:
            print(f"Error saving canon to S3: {e}")

    def update_character(self, name: str, info: Dict):
        norm_key = normalize_key(name)
        if "metadata" not in self.data: self.data["metadata"] = {"original_keys": {}}
        self.data["metadata"]["original_keys"][norm_key] = name # Save display name
        
        if norm_key not in self.data["characters"]:
            self.data["characters"][norm_key] = {}
        self.data["characters"][norm_key].update(info)
        self.save()

    def update_style(self, style_info: Dict):
        self.data["style"].update(style_info)
        self.save()

    def update_scenery(self, name: str, info: Dict):
        norm_key = normalize_key(name)
        if "metadata" not in self.data: self.data["metadata"] = {"original_keys": {}}
        self.data["metadata"]["original_keys"][norm_key] = name # Save display name

        if norm_key not in self.data["sceneries"]:
            self.data["sceneries"][norm_key] = {}
        self.data["sceneries"][norm_key].update(info)
        self.save()
