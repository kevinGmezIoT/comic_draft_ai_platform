import requests
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Project, Page, Panel, Character, Scenery

class GenerateComicView(APIView):
    def post(self, request, project_id):
        try:
            project = Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

        if request.data.get("plan_only", False):
            # FAST PATH: Generación síncrona de maquetación (cuadros en blanco)
            max_pages = int(request.data.get("max_pages", 1))
            panels_per_page = int(request.data.get("max_panels_per_page", 4))
            target_page_num = request.data.get("page_number") # Opcional: solo regenerar una página

            if target_page_num is not None:
                target_page_num = int(target_page_num)
                # Asegurar que todas las páginas hasta max_pages existan
                for p_num in range(1, max_pages + 1):
                    Page.objects.get_or_create(project=project, page_number=p_num)

                # Regenerar SOLO una página específica
                page = Page.objects.get(project=project, page_number=target_page_num)
                page.panels.all().delete()
                
                for i in range(panels_per_page):
                    # Layout grid base
                    row = i // 2
                    col = i % 2
                    rows_count = (panels_per_page + 1) // 2
                    cols_count = 2 if panels_per_page > 1 else 1
                    w = 100 / cols_count
                    h = 100 / rows_count
                    
                    Panel.objects.create(
                        page=page,
                        order=i,
                        prompt="Cinematic comic panel placeholder",
                        scene_description=f"Escena {((target_page_num-1)*panels_per_page) + i + 1}",
                        layout={"x": col*w, "y": row*h, "w": w, "h": h},
                        status="pending"
                    )
                project.status = "completed"
                project.save()
                return Response({"status": "completed", "message": f"Page {target_page_num} redesigned."}, status=status.HTTP_200_OK)

            # RESET GLOBAL: El usuario pide regenerar TODO
            if not request.data.get("skip_cleaning", False):
                project.pages.all().delete()
            
            for p_num in range(1, max_pages + 1):
                page, _ = Page.objects.get_or_create(project=project, page_number=p_num)
                
                for i in range(panels_per_page):
                    row = i // 2
                    col = i % 2
                    rows_count = (panels_per_page + 1) // 2
                    cols_count = 2 if panels_per_page > 1 else 1
                    w = 100 / cols_count
                    h = 100 / rows_count
                    
                    Panel.objects.create(
                        page=page,
                        order=i,
                        prompt="Cinematic comic panel placeholder",
                        scene_description=f"Escena {((p_num-1)*panels_per_page) + i + 1}",
                        layout={"x": col*w, "y": row*h, "w": w, "h": h},
                        status="pending"
                    )

            project.status = "completed"
            project.save()
            return Response({"status": "completed", "message": f"Layout designed for {max_pages} pages."}, status=status.HTTP_200_OK)

        # Enviar a cola del Agente (Solo para generación de arte real)
        agent_url = f"{settings.AGENT_SERVICE_URL}/generate"
        payload = {
            "project_id": str(project.id),
            "sources": ["s3://comic-draft/sources/guion.pdf"], # Simulación
            "max_pages": request.data.get("max_pages", 3),
            "max_panels": request.data.get("max_panels"),
            "max_panels_per_page": request.data.get("max_panels_per_page", 4),
            "layout_style": request.data.get("layout_style", "dynamic"),
            "plan_only": False,
            "panels": request.data.get("panels", []),
            "global_context": {
                "world_bible": project.world_bible,
                "style_guide": project.style_guide,
                "characters": [{
                    "name": c.name,
                    "description": c.description,
                    "metadata": c.metadata
                } for c in project.characters.all()],
                "sceneries": [{
                    "name": s.name,
                    "description": s.description,
                    "metadata": s.metadata
                } for s in project.sceneries.all()]
            }
        }

        print(f"DEBUG: Enviando peticion al Agent en {agent_url}")
        try:
            project.status = "generating"
            project.last_error = None
            project.save()
            response = requests.post(agent_url, json=payload, timeout=10)
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
            
            pages_data = []
            for page in pages:
                # Obtener paneles de esta página
                page_panels = []
                for panel in page.panels.all().order_by('order'):
                    page_panels.append({
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
                    "panels": page_panels
                })
            
            return Response({
                "id": project.id,
                "name": project.name,
                "description": project.description,
                "world_bible": project.world_bible,
                "style_guide": project.style_guide,
                "status": project.status,
                "last_error": project.last_error,
                "pages": pages_data,
                "notes": [{
                    "id": n.id,
                    "title": n.title,
                    "content": n.content,
                    "file_url": n.file_url,
                    "note_type": n.note_type
                } for n in project.notes.all()],
                "characters": [{
                    "id": c.id,
                    "name": c.name,
                    "description": c.description,
                    "metadata": c.metadata,
                    "image_url": c.image_url
                } for c in project.characters.all()],
                "sceneries": [{
                    "id": s.id,
                    "name": s.name,
                    "description": s.description,
                    "metadata": s.metadata,
                    "image_url": s.image_url
                } for s in project.sceneries.all()]
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

            result = request.data.get('result', {})
            # Organizar por páginas y paneles
            panels_data = result.get('panels', [])
            
            if not panels_data or len(panels_data) == 0:
                project.status = 'failed'
                project.last_error = "El Agente no pudo generar una maquetación válida (0 paneles)."
                project.save()
                return Response({"status": "no_panels_found"}, status=status.HTTP_200_OK)

            # Agrupar por página
            pages_map = {}
            for p_data in panels_data:
                p_num = p_data.get('page_number', 1)
                if p_num not in pages_map:
                    page, _ = Page.objects.get_or_create(project=project, page_number=p_num)
                    pages_map[p_num] = page
                
                # Para este prototipo, usamos order + page como clave única de panel
                Panel.objects.update_or_create(
                    page=pages_map[p_num],
                    order=p_data.get('order_in_page', 0),
                    defaults={
                        "prompt": p_data['prompt'],
                        "scene_description": p_data.get('scene_description', ''),
                        "image_url": p_data.get('image_url', ''),
                        "balloons": p_data.get('balloons', []),
                        "layout": p_data.get('layout', {}),
                        "status": "completed"
                    }
                )
            
            # Guardar URLs de páginas fusionadas (Organic Merge)
            merged_pages_data = result.get('merged_pages', [])
            for m_data in merged_pages_data:
                p_num = m_data.get('page_number')
                page = Page.objects.filter(project=project, page_number=p_num).first()
                if page:
                    page.merged_image_url = m_data.get('image_url', '')
                    page.save()

            # FINALMENTE marcar como completado después de salvar todo
            project.status = 'completed'
            project.last_error = None
            project.save()
            
            return Response({"status": "received"}, status=status.HTTP_200_OK)
        except Project.DoesNotExist:
            return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

class CreateProjectView(APIView):
    def get(self, request):
        projects = Project.objects.all().order_by('-created_at')
        return Response([{
            "id": p.id,
            "name": p.name,
            "status": p.status,
            "created_at": p.created_at
        } for p in projects])

    def post(self, request):
        name = request.data.get('name')
        if not name:
            return Response({"error": "Name is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        project = Project.objects.create(
            name=name,
            description=request.data.get('description', '')
        )
        return Response({"id": project.id, "name": project.name}, status=status.HTTP_201_CREATED)

class CharacterListView(APIView):
    def get(self, request, project_id):
        characters = Character.objects.filter(project_id=project_id)
        return Response([{
            "id": c.id,
            "name": c.name,
            "description": c.description,
            "image_url": c.image_url
        } for c in characters])

class CharacterDetailView(APIView):
    def get(self, request, character_id):
        try:
            c = Character.objects.get(id=character_id)
            return Response({
                "id": c.id,
                "name": c.name,
                "description": c.description,
                "metadata": c.metadata,
                "image_url": c.image_url
            })
        except Character.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

    def patch(self, request, character_id):
        try:
            c = Character.objects.get(id=character_id)
            c.name = request.data.get('name', c.name)
            c.description = request.data.get('description', c.description)
            c.metadata = request.data.get('metadata', c.metadata)
            c.image_url = request.data.get('image_url', c.image_url)
            c.save()
            return Response({"status": "updated"})
        except Character.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, character_id):
        try:
            c = Character.objects.get(id=character_id)
            c.delete()
            return Response({"status": "deleted"}, status=status.HTTP_204_NO_CONTENT)
        except Character.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

class CharacterCreateView(APIView):
    def post(self, request, project_id):
        try:
            project = Project.objects.get(id=project_id)
            character = Character.objects.create(
                project=project,
                name=request.data.get('name'),
                description=request.data.get('description', ''),
                metadata=request.data.get('metadata', {}),
                image_url=request.data.get('image_url', '')
            )
            return Response({"id": character.id}, status=status.HTTP_201_CREATED)
        except Project.DoesNotExist:
            return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

class SceneryListView(APIView):
    def get(self, request, project_id):
        sceneries = Scenery.objects.filter(project_id=project_id)
        return Response([{
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "image_url": s.image_url
        } for s in sceneries])

class SceneryDetailView(APIView):
    def get(self, request, scenery_id):
        try:
            s = Scenery.objects.get(id=scenery_id)
            return Response({
                "id": s.id,
                "name": s.name,
                "description": s.description,
                "metadata": s.metadata,
                "image_url": s.image_url
            })
        except Scenery.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

    def patch(self, request, scenery_id):
        try:
            s = Scenery.objects.get(id=scenery_id)
            s.name = request.data.get('name', s.name)
            s.description = request.data.get('description', s.description)
            s.metadata = request.data.get('metadata', s.metadata)
            s.image_url = request.data.get('image_url', s.image_url)
            s.save()
            return Response({"status": "updated"})
        except Scenery.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, scenery_id):
        try:
            s = Scenery.objects.get(id=scenery_id)
            s.delete()
            return Response({"status": "deleted"}, status=status.HTTP_204_NO_CONTENT)
        except Scenery.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

class SceneryCreateView(APIView):
    def post(self, request, project_id):
        try:
            project = Project.objects.get(id=project_id)
            scenery = Scenery.objects.create(
                project=project,
                name=request.data.get('name'),
                description=request.data.get('description', ''),
                metadata=request.data.get('metadata', {}),
                image_url=request.data.get('image_url', '')
            )
            return Response({"id": scenery.id}, status=status.HTTP_201_CREATED)
        except Project.DoesNotExist:
            return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)
class UpdatePanelView(APIView):
    """Actualiza campos de un panel específico"""
    def patch(self, request, panel_id):
        try:
            panel = Panel.objects.get(id=panel_id)
            panel.prompt = request.data.get('prompt', panel.prompt)
            panel.scene_description = request.data.get('scene_description', panel.scene_description)
            panel.balloons = request.data.get('balloons', panel.balloons)
            panel.save()
            return Response({"status": "updated", "id": panel.id}, status=status.HTTP_200_OK)
        except Panel.DoesNotExist:
            return Response({"error": "Panel not found"}, status=status.HTTP_404_NOT_FOUND)

class RegeneratePanelView(APIView):
    """Dispara la regeneración de la imagen de un panel"""
    def post(self, request, panel_id):
        try:
            panel = Panel.objects.get(id=panel_id)
            project = panel.page.project
            
            agent_url = f"{settings.AGENT_SERVICE_URL}/regenerate-panel"
            payload = {
                "project_id": str(project.id),
                "panel_id": panel.id,
                "prompt": panel.prompt,
                "scene_description": panel.scene_description,
                "balloons": panel.balloons
            }
            
            project.status = "generating"
            project.save()
            
            response = requests.post(agent_url, json=payload, timeout=10)
            return Response(response.json(), status=status.HTTP_202_ACCEPTED)
        except Panel.DoesNotExist:
            return Response({"error": "Panel not found"}, status=status.HTTP_404_NOT_FOUND)

class RegenerateMergedPagesView(APIView):
    """Dispara la regeneración del organic merge de una página o proyecto"""
    def post(self, request, project_id):
        try:
            project = Project.objects.get(id=project_id)
            instructions = request.data.get('instructions', '')
            
            agent_url = f"{settings.AGENT_SERVICE_URL}/regenerate-merge"
            payload = {
                "project_id": str(project.id),
                "instructions": instructions
            }
            
            project.status = "generating"
            project.save()
            
            response = requests.post(agent_url, json=payload, timeout=10)
            return Response(response.json(), status=status.HTTP_202_ACCEPTED)
        except Project.DoesNotExist:
            return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

class ProjectNoteView(APIView):
    def post(self, request, project_id):
        try:
            project = Project.objects.get(id=project_id)
            note = ProjectNote.objects.create(
                project=project,
                title=request.data.get('title'),
                content=request.data.get('content', ''),
                file_url=request.data.get('file_url', ''),
                file_path=request.data.get('file_path', ''),
                note_type=request.data.get('note_type', 'general')
            )
            return Response({"id": str(note.id)}, status=status.HTTP_201_CREATED)
        except Project.DoesNotExist:
            return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

class ProjectNoteDetailView(APIView):
    def patch(self, request, note_id):
        try:
            note = ProjectNote.objects.get(id=note_id)
            note.title = request.data.get('title', note.title)
            note.content = request.data.get('content', note.content)
            note.file_url = request.data.get('file_url', note.file_url)
            note.file_path = request.data.get('file_path', note.file_path)
            note.note_type = request.data.get('note_type', note.note_type)
            note.save()
            return Response({"status": "updated"})
        except ProjectNote.DoesNotExist:
            return Response({"error": "Note not found"}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, note_id):
        try:
            note = ProjectNote.objects.get(id=note_id)
            note.delete()
            return Response({"status": "deleted"}, status=status.HTTP_204_NO_CONTENT)
        except ProjectNote.DoesNotExist:
            return Response({"error": "Note not found"}, status=status.HTTP_404_NOT_FOUND)

class PanelLayoutUpdateView(APIView):
    def patch(self, request, panel_id):
        try:
            panel = Panel.objects.get(id=panel_id)
            panel.layout = request.data.get('layout', panel.layout)
            panel.save()
            return Response({"status": "layout updated"})
        except Panel.DoesNotExist:
            return Response({"error": "Panel not found"}, status=status.HTTP_404_NOT_FOUND)

class ProjectUpdateView(APIView):
    def patch(self, request, project_id):
        try:
            project = Project.objects.get(id=project_id)
            project.name = request.data.get('name', project.name)
            project.description = request.data.get('description', project.description)
            project.world_bible = request.data.get('world_bible', project.world_bible)
            project.style_guide = request.data.get('style_guide', project.style_guide)
            project.save()
            return Response({"status": "updated"})
        except Project.DoesNotExist:
            return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

class DeletePanelView(APIView):
    def delete(self, request, panel_id):
        try:
            panel = Panel.objects.get(id=panel_id)
            page = panel.page
            current_order = panel.order
            panel.delete()
            
            # Reordenar paneles posteriores en la misma página
            subsequent_panels = page.panels.filter(order__gt=current_order).order_by('order')
            for p in subsequent_panels:
                p.order -= 1
                p.save()
                
            return Response({"status": "deleted and reordered"}, status=status.HTTP_200_OK)
        except Panel.DoesNotExist:
            return Response({"error": "Panel not found"}, status=status.HTTP_404_NOT_FOUND)
