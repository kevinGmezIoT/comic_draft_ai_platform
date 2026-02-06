from django.db import models
import uuid

class Project(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class Page(models.Model):
    project = models.ForeignKey(Project, related_name='pages', on_delete=models.CASCADE)
    page_number = models.IntegerField()
    layout_data = models.JSONField(default=dict) # Posiciones de paneles

class Panel(models.Model):
    page = models.ForeignKey(Page, related_name='panels', on_delete=models.CASCADE)
    order = models.IntegerField()
    prompt = models.TextField()
    image_url = models.URLField(max_length=1000, blank=True)
    status = models.CharField(max_length=50, default="pending")
    version = models.IntegerField(default=1)
    # Metadatos adicionales para consistencia
    character_refs = models.JSONField(default=list, blank=True)

class Asset(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    file_path = models.CharField(max_length=500)
    asset_type = models.CharField(max_length=50) # character, setting, script
