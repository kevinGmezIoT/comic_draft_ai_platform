from django.contrib import admin
from django.urls import path
from apps.projects.views import GenerateComicView, AgentCallbackView, ProjectDetailView, UpdatePanelView, RegeneratePanelView, RegenerateMergedPagesView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/projects/<uuid:project_id>/', ProjectDetailView.as_view()),
    path('api/projects/<uuid:project_id>/generate/', GenerateComicView.as_view()),
    path('api/projects/<uuid:project_id>/callback/', AgentCallbackView.as_view()),
    path('api/projects/<uuid:project_id>/regenerate-merge/', RegenerateMergedPagesView.as_view()),
    path('api/panels/<int:panel_id>/update/', UpdatePanelView.as_view()),
    path('api/panels/<int:panel_id>/regenerate/', RegeneratePanelView.as_view()),
]
