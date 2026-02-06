import requests
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Project, Page, Panel

class GenerateComicView(APIView):
    def post(self, request, project_id):
        try:
            project = Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

        # Enviar a cola del Agente
        agent_url = f"{settings.AGENT_SERVICE_URL}/generate"
        payload = {
            "project_id": str(project.id),
            "sources": ["s3://comic-draft/sources/guion.pdf"] # Simulación
        }

        try:
            # Ahora la respuesta es inmediata (202 Accepted)
            response = requests.post(agent_url, json=payload, timeout=10)
            return Response(response.json(), status=status.HTTP_202_ACCEPTED)
        except requests.exceptions.RequestException as e:
            return Response({"error": f"Agent service unavailable: {str(e)}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

class ProjectDetailView(APIView):
    """Obtén el estado actual del cómic (páginas y paneles)"""
    def get(self, request, project_id):
        try:
            project = Project.objects.get(id=project_id)
            pages = project.pages.all().order_by('page_number')
            
            panels_list = []
            for page in pages:
                for panel in page.panels.all().order_by('order'):
                    panels_list.append({
                        "id": panel.id,
                        "page": page.page_number,
                        "order": panel.order,
                        "prompt": panel.prompt,
                        "image_url": panel.image_url,
                        "status": panel.status
                    })
            
            return Response({
                "id": project.id,
                "name": project.name,
                "panels": panels_list
            })
        except Project.DoesNotExist:
            return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

class AgentCallbackView(APIView):
    """Webhook para que el Agente notifique resultados"""
    def post(self, request, project_id):
        try:
            project = Project.objects.get(id=project_id)
            result = request.data.get('result')
            
            # Limpiar versiones previas para este prototipo o manejar versionado
            Page.objects.filter(project=project).delete()
            
            # Organizar por páginas y paneles
            panels_data = result.get('panels', [])
            # Agrupar por página
            pages = {}
            for p_data in panels_data:
                p_num = p_data.get('page_number', 1)
                if p_num not in pages:
                    pages[p_num] = Page.objects.create(project=project, page_number=p_num)
                
                Panel.objects.create(
                    page=pages[p_num],
                    order=p_data.get('order_in_page', 0),
                    prompt=p_data['prompt'],
                    image_url=p_data['image_url'],
                    status="completed"
                )
            
            return Response({"status": "received"}, status=status.HTTP_200_OK)
        except Project.DoesNotExist:
            return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)
