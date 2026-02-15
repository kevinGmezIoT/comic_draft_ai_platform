from django.contrib import admin
from django.urls import path
from apps.projects.views import (
    GenerateComicView, AgentCallbackView, ProjectDetailView, 
    UpdatePanelView, RegeneratePanelView, RegenerateMergedPagesView,
    CreateProjectView, ProjectUpdateView, PanelUploadReferenceImageView,
    CharacterListView, CharacterCreateView, CharacterDetailView,
    SceneryListView, SceneryCreateView, SceneryDetailView,
    ProjectNoteView, ProjectNoteDetailView, PanelLayoutUpdateView,
    DeletePanelView
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/projects/', CreateProjectView.as_view()),
    path('api/projects/<uuid:project_id>/', ProjectDetailView.as_view()),
    path('api/projects/<uuid:project_id>/update/', ProjectUpdateView.as_view()),
    path('api/projects/<uuid:project_id>/generate/', GenerateComicView.as_view()),
    path('api/projects/<uuid:project_id>/callback/', AgentCallbackView.as_view()),
    path('api/projects/<uuid:project_id>/regenerate-merge/', RegenerateMergedPagesView.as_view()),
    path('api/projects/<uuid:project_id>/characters/', CharacterListView.as_view()),
    path('api/projects/<uuid:project_id>/characters/create/', CharacterCreateView.as_view()),
    path('api/projects/characters/<int:character_id>/', CharacterDetailView.as_view()),
    path('api/projects/<uuid:project_id>/sceneries/', SceneryListView.as_view()),
    path('api/projects/<uuid:project_id>/sceneries/create/', SceneryCreateView.as_view()),
    path('api/projects/sceneries/<int:scenery_id>/', SceneryDetailView.as_view()),
    path('api/projects/<uuid:project_id>/notes/', ProjectNoteView.as_view()),
    path('api/projects/notes/<uuid:note_id>/', ProjectNoteDetailView.as_view()),
    path('api/panels/<int:panel_id>/update-layout/', PanelLayoutUpdateView.as_view()),
    path('api/panels/<int:panel_id>/update/', UpdatePanelView.as_view()),
    path('api/panels/<int:panel_id>/upload-reference/', PanelUploadReferenceImageView.as_view()),
    path('api/panels/<int:panel_id>/regenerate/', RegeneratePanelView.as_view()),
    path('api/panels/<int:panel_id>/', DeletePanelView.as_view()),
]
