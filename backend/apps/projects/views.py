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
            "sources": ["s3://comic-draft/sources/guion.pdf"], # Simulación
            "max_pages": request.data.get("max_pages", 3),
            "max_panels": request.data.get("max_panels"),
            "layout_style": request.data.get("layout_style", "dynamic")
        }

        print(f"DEBUG: Enviando peticion al Agent en {agent_url}")
        try:
            project.status = "generating"
            project.last_error = None
            project.save()
            response = requests.post(agent_url, json=payload, timeout=10)
            print(f"DEBUG: Agent response status: {response.status_code}")
            return Response(response.json(), status=status.HTTP_202_ACCEPTED)
        except requests.exceptions.RequestException as e:
            print(f"ERROR: Fallo al conectar con el Agent: {str(e)}")
            return Response({"error": f"Agent service unavailable: {str(e)}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

class ProjectDetailView(APIView):
    """Obtén el estado actual del cómic (páginas y paneles)"""
    def get(self, request, project_id):
        try:
            project = Project.objects.get(id=project_id)
            pages = project.pages.all().order_by('page_number')
            
            panels_list = []
            pages_data = []
            for page in pages:
                for panel in page.panels.all().order_by('order'):
                    panels_list.append({
                        "id": panel.id,
                        "page_number": page.page_number,
                        "order": panel.order,
                        "prompt": panel.prompt,
                        "scene_description": panel.scene_description,
                        "image_url": panel.image_url,
                        "status": panel.status,
                        "balloons": panel.balloons,
                        "layout": panel.layout
                    })
                
                pages_data.append({
                    "page_number": page.page_number,
                    "merged_image_url": page.merged_image_url,
                    "panels": [p for p in panels_list if p["page_number"] == page.page_number]
                })
            
            return Response({
                "id": project.id,
                "name": project.name,
                "status": project.status,
                "last_error": project.last_error,
                "pages": pages_data
            })
        except Project.DoesNotExist:
            return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

class AgentCallbackView(APIView):
    """Webhook para que el Agente notifique resultados"""
    def post(self, request, project_id):
        try:
            project = Project.objects.get(id=project_id)
            status_received = request.data.get('status')
            
            if status_received == 'failed':
                error_msg = request.data.get('error', 'Unknown Error')
                project.status = 'failed'
                project.last_error = error_msg
                project.save()
                return Response({"status": "error_logged"}, status=status.HTTP_200_OK)

            result = request.data.get('result')
            project.status = 'completed'
            project.last_error = None
            project.save()
            
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
                    scene_description=p_data.get('scene_description', ''),
                    image_url=p_data.get('image_url', ''),
                    balloons=p_data.get('balloons', []),
                    layout=p_data.get('layout', {}),
                    status="completed"
                )
            
            # Guardar URLs de páginas fusionadas (Organic Merge)
            merged_pages_data = result.get('merged_pages', [])
            for m_data in merged_pages_data:
                p_num = m_data.get('page_number')
                if p_num in pages:
                    pages[p_num].merged_image_url = m_data.get('image_url', '')
                    pages[p_num].save()
            
            return Response({"status": "received"}, status=status.HTTP_200_OK)
        except Project.DoesNotExist:
            return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)
