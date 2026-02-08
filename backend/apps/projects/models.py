from django.db import models
import uuid
import os

def get_project_id(instance):
    if hasattr(instance, 'project'):
        return str(instance.project.id)
    if hasattr(instance, 'page'):
        return str(instance.page.project.id)
    return "unknown"

def page_upload_path(instance, filename):
    return f"projects/{get_project_id(instance)}/merged/{filename}"

def panel_upload_path(instance, filename):
    return f"projects/{get_project_id(instance)}/panels/{filename}"

def character_upload_path(instance, filename):
    return f"projects/{get_project_id(instance)}/characters/{filename}"

def scenery_upload_path(instance, filename):
    return f"projects/{get_project_id(instance)}/sceneries/{filename}"

def note_upload_path(instance, filename):
    return f"projects/{get_project_id(instance)}/notes/{filename}"

class Project(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    status = models.CharField(max_length=50, default="idle") # idle, generating, failed, completed
    last_error = models.TextField(blank=True, null=True)
    world_bible = models.TextField(blank=True, help_text="Información global (nombres, estilos, localización, etc.)")
    style_guide = models.TextField(blank=True, help_text="Instrucciones de estilo visual constantes")

    def __str__(self):
        return self.name

class Page(models.Model):
    project = models.ForeignKey(Project, related_name='pages', on_delete=models.CASCADE)
    page_number = models.IntegerField()
    layout_data = models.JSONField(default=dict) # Posiciones de paneles
    merged_image = models.ImageField(upload_to=page_upload_path, max_length=1000, blank=True, null=True)

    @property
    def merged_image_url(self):
        if self.merged_image:
            return self.merged_image.url
        return ""

class Panel(models.Model):
    page = models.ForeignKey(Page, related_name='panels', on_delete=models.CASCADE)
    order = models.IntegerField()
    prompt = models.TextField()
    scene_description = models.TextField(blank=True)
    image = models.ImageField(upload_to=panel_upload_path, max_length=1000, blank=True, null=True)

    @property
    def image_url(self):
        if self.image:
            return self.image.url
        return ""
    status = models.CharField(max_length=50, default="pending")
    version = models.IntegerField(default=1)
    # Metadatos adicionales para consistencia y diálogo
    balloons = models.JSONField(default=list, blank=True)
    layout = models.JSONField(default=dict, blank=True)
    character_refs = models.JSONField(default=list, blank=True)

class Asset(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    file_path = models.CharField(max_length=500)
    asset_type = models.CharField(max_length=50) # character, setting, script

class Character(models.Model):
    project = models.ForeignKey(Project, related_name='characters', on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True) # Para rasgos especificos, amigos, etc.
    image = models.ImageField(upload_to=character_upload_path, max_length=1000, blank=True, null=True)

    @property
    def image_url(self):
        if self.image:
            return self.image.url
        return ""
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.project.name})"

class Scenery(models.Model):
    project = models.ForeignKey(Project, related_name='sceneries', on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    image = models.ImageField(upload_to=scenery_upload_path, max_length=1000, blank=True, null=True)

    @property
    def image_url(self):
        if self.image:
            return self.image.url
        return ""
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.project.name})"

class ProjectNote(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, related_name='notes', on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    content = models.TextField(blank=True)
    file = models.FileField(upload_to=note_upload_path, max_length=1000, blank=True, null=True)

    @property
    def file_url(self):
        if self.file:
            return self.file.url
        return ""
    note_type = models.CharField(max_length=50, default="general") # global, character_note, scenery_note, style
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} ({self.project.name})"
