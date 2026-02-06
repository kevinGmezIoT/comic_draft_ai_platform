from django.contrib import admin
from django.urls import path
from apps.projects.views import GenerateComicView, AgentCallbackView, ProjectDetailView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/projects/<uuid:project_id>/', ProjectDetailView.as_view()),
    path('api/projects/<uuid:project_id>/generate/', GenerateComicView.as_view()),
    path('api/projects/<uuid:project_id>/callback/', AgentCallbackView.as_view()),
]
