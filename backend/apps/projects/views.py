import requests
import threading
from django.conf import settings
from .agent_utils import BedrockAgentClient
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Project, Page, Panel, Character, Scenery
from .result_processor import process_agent_result

class GenerateComicView(APIView):
    def post(self, request, project_id):
        try:
            project = Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

        if request.data.get("plan_only", False):
            # FAST PATH: Generación síncrona de maquetación (cuadros en blanco)
            try:
                # Usar variables locales en lugar de atributos del modelo inexistentes
                req_max_pages = request.data.get("max_pages")
                max_pages = int(req_max_pages) if req_max_pages is not None else project.pages.count() or 1
                
                raw_mppp = request.data.get("panels_per_page")
                print(f"DEBUG: [PLAN ONLY] panels_per_page raw: {raw_mppp}")

                if raw_mppp == 'auto' or raw_mppp is None:
                    panels_per_page = None
                else:
                    panels_per_page = int(raw_mppp)

                # Si es AUTO (None), no podemos usar el FAST PATH síncrono porque requiere IA. 
                # Delegamos al Agente (Slow Path) para que haga el trabajo inteligente.
                if panels_per_page is None:
                    print("DEBUG: [PLAN ONLY] IA Decide detected. Routing to Agent Slow Path.")
                    pass # Continuar hacia la lógica del agente abajo
                else:
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

                    # RESET GLOBAL: El usuario pide regenerar TODO (Sync Path)
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
            except (ValueError, TypeError) as e:
                print(f"DEBUG: Fast path error or IA Decide requirement: {e}")
                # Si falla o es IA decide, caemos al slow path del agente
                pass

        # Sincronizar preferencias del usuario con el modelo persistente
        req_max_pages = request.data.get("max_pages")
        if req_max_pages is not None:
            project.max_pages = int(req_max_pages)
        

        req_max_panels = request.data.get("max_panels")
        if req_max_panels is not None and str(req_max_panels).isdigit():
            project.max_panels = int(req_max_panels)

        project.layout_style = request.data.get("layout_style", project.layout_style)
        project.save()

        plan_only = request.data.get("plan_only", False)
        skip_agent = request.data.get("skip_agent", False)

        if plan_only and skip_agent:
            return Response({
                "status": "skipped",
                "project_id": project.id,
                "layout_settings": {
                    "max_pages": project.max_pages,
                    "layout_style": project.layout_style
                }
            })

        # Enviar a cola del Agente (Solo para generación de arte real)
        agent_url = f"{settings.AGENT_SERVICE_URL}/generate"
        # Obtener archivos fuente reales (Guión de las notas del proyecto)
        from .models import ProjectNote
        script_note = project.notes.filter(note_type="script").first()
        sources = []
        if script_note and script_note.file:
            # Si usamos S3, .url nos da la URL completa (puede ser presigned)
            # El Agente puede manejar URLs de S3 directamente si tiene permisos o si la URL es pública/presigned
            sources.append(script_note.file.url)
        else:
            # Fallback por si no hay archivo, pero ya no es hardcoded a un bucket fijo ajeno
            sources = state_sources if (state_sources := request.data.get("sources")) else []
        
        payload = {
            "project_id": str(project.id),
            "sources": sources,
            "max_pages": project.max_pages,
            "max_panels": len(request.data.get("panels", [])),
            "layout_style": project.layout_style,
            "plan_only": request.data.get("plan_only", False),
            "panels": request.data.get("panels", []),
            "global_context": {
                "description": project.description,
                "world_bible": project.world_bible,
                "style_guide": project.style_guide,
                "characters": [{
                    "name": c.name,
                    "description": c.description,
                    "metadata": c.metadata,
                    "image_url": request.build_absolute_uri(c.image.url) if c.image else ""
                } for c in project.characters.all()],
                "sceneries": [{
                    "name": s.name,
                    "description": s.description,
                    "metadata": s.metadata,
                    "image_url": request.build_absolute_uri(s.image.url) if s.image else ""
                } for s in project.sceneries.all()]
            }
        }

        import json
        print(f"DEBUG: Payload sent to Agent: {json.dumps(payload, indent=2)}")

        print(f"DEBUG: Enviando peticion al Bedrock Agent: {project.id}")
        try:
            project.status = "generating"
            project.last_error = None
            project.save()

            # Invocar al agente en un hilo separado para no bloquear la respuesta HTTP
            # El agente notificará al AgentCallbackView cuando termine
            client = BedrockAgentClient()
            thread = threading.Thread(
                target=client.invoke,
                args=(payload, project.id)
            )
            thread.start()

            return Response({
                "project_id": str(project.id),
                "status": "queued",
                "message": "Generation process started in Bedrock Agent"
            }, status=status.HTTP_202_ACCEPTED)
        except Exception as e:
            print(f"ERROR: Fallo al invocar al Bedrock Agent: {str(e)}")
            return Response({"error": f"Bedrock Agent error: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
                "layout_style": project.layout_style,
                "max_pages": project.max_pages,
                "max_panels": project.max_panels,
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
        print(f"DEBUG: [CALLBACK] Received request for project {project_id}")
        try:
            result = process_agent_result(project_id, request.data)
            
            if result.get("status") == "success":
                return Response({"status": "received"}, status=status.HTTP_200_OK)
            else:
                return Response(result, status=status.HTTP_400_BAD_REQUEST)
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
            description=request.data.get('description', ''),
            world_bible=request.data.get('world_bible', ''),
            style_guide=request.data.get('style_guide', '')
        )

        # Si viene un archivo de guión, crearlo como nota
        script_file = request.FILES.get('script_file')
        if script_file:
            from .models import ProjectNote
            note = ProjectNote.objects.create(
                project=project,
                title="Guión Original",
                file=script_file,
                note_type="script"
            )
            print(f"DEBUG S3: Guión subido correctamente. URL: {note.file.url}")

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
            if 'image_url' in request.data:
                c.image.name = request.data.get('image_url')
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
            )
            image_file = request.FILES.get('image')
            if image_file:
                character.image = image_file
                print(f"DEBUG S3: Subiendo imagen de personaje '{character.name}'...")
            elif request.data.get('image_url'):
                character.image.name = request.data.get('image_url')
            
            character.save()
            if image_file:
                print(f"DEBUG S3: Imagen de personaje subida. URL: {character.image.url}")
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
            if 'image_url' in request.data:
                s.image.name = request.data.get('image_url')
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
            )
            image_file = request.FILES.get('image')
            if image_file:
                scenery.image = image_file
                print(f"DEBUG S3: Subiendo imagen de escenario '{scenery.name}'...")
            elif request.data.get('image_url'):
                scenery.image.name = request.data.get('image_url')
            
            scenery.save()
            if image_file:
                print(f"DEBUG S3: Imagen de escenario subida. URL: {scenery.image.url}")
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
            panel.panel_style = request.data.get('panel_style', panel.panel_style)
            
            # Handle reference image if provided via URL or path
            if 'reference_image_url' in request.data:
                panel.reference_image.name = request.data.get('reference_image_url')
            
            panel.save()
            return Response({"status": "updated", "id": panel.id}, status=status.HTTP_200_OK)
        except Panel.DoesNotExist:
            return Response({"error": "Panel not found"}, status=status.HTTP_404_NOT_FOUND)

class RegeneratePanelView(APIView):
    """Dispara la regeneración de la imagen de un panel con contexto mejorado"""
    def post(self, request, panel_id):
        try:
            panel = Panel.objects.get(id=panel_id)
            project = panel.page.project
            
            instructions = request.data.get('instructions', '')
            use_current_as_base = request.data.get('use_current_as_base', False)
            
            payload = {
                "action": "regenerate_panel",
                "project_id": str(project.id),
                "panel_id": panel.id,
                "prompt": panel.prompt,
                "scene_description": panel.scene_description,
                "balloons": panel.balloons,
                "panel_style": request.data.get('panel_style', panel.panel_style),
                "instructions": instructions,
                "current_image_url": request.build_absolute_uri(panel.image.url) if panel.image and use_current_as_base else None,
                "reference_image_url": request.build_absolute_uri(panel.reference_image.url) if panel.reference_image else None,
                "panels": [{
                    "id": p.id,
                    "page_number": p.page.page_number,
                    "order_in_page": p.order,
                    "prompt": p.prompt,
                    "scene_description": p.scene_description,
                    "image_url": p.image.name if p.image else "",
                    "status": p.status,
                    "balloons": p.balloons,
                    "layout": p.layout,
                    "character_refs": p.character_refs
                } for p in Panel.objects.filter(page__project=project)],
                "global_context": {
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
            
            project.status = "generating"
            project.save()

            print("PAYLOAD:", payload)
            
            client = BedrockAgentClient()
            threading.Thread(target=client.invoke, args=(payload, project.id)).start()
            
            return Response({"status": "queued", "panel_id": panel.id}, status=status.HTTP_202_ACCEPTED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class RegenerateMergedPagesView(APIView):
    """Dispara la regeneración del organic merge de una página o proyecto"""
    def post(self, request, project_id):
        try:
            project = Project.objects.get(id=project_id)
            instructions = request.data.get('instructions', '')
            
            agent_url = f"{settings.AGENT_SERVICE_URL}/regenerate-merge"
            payload = {
                "action": "regenerate_merge",
                "project_id": str(project.id),
                "instructions": instructions,
                "world_model_summary": project.world_model_summary,
                "panels": [{
                    "id": p.id,
                    "page_number": p.page.page_number,
                    "order_in_page": p.order,
                    "prompt": p.prompt,
                    "scene_description": p.scene_description,
                    "image_url": p.image.name if p.image else "",
                    "status": p.status,
                    "balloons": p.balloons,
                    "layout": p.layout,
                    "character_refs": p.character_refs
                } for p in Panel.objects.filter(page__project=project)],
                "global_context": {
                    "style_guide": project.style_guide,
                    "characters": [{
                        "name": c.name,
                        "description": c.description,
                        "metadata": c.metadata,
                        "image_url": request.build_absolute_uri(c.image.url) if c.image else ""
                    } for c in project.characters.all()],
                    "sceneries": [{
                        "name": s.name,
                        "description": s.description,
                        "metadata": s.metadata,
                        "image_url": request.build_absolute_uri(s.image.url) if s.image else ""
                    } for s in project.sceneries.all()]
                }
            }
            
            project.status = "generating"
            project.save()
            
            client = BedrockAgentClient()
            threading.Thread(target=client.invoke, args=(payload, project.id)).start()
            
            return Response({"status": "queued", "project_id": str(project.id)}, status=status.HTTP_202_ACCEPTED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class ProjectNoteView(APIView):
    def post(self, request, project_id):
        try:
            project = Project.objects.get(id=project_id)
            note = ProjectNote.objects.create(
                project=project,
                title=request.data.get('title'),
                content=request.data.get('content', ''),
                note_type=request.data.get('note_type', 'general')
            )
            if request.data.get('file_url'):
                note.file.name = request.data.get('file_url')
            elif request.data.get('file_path'):
                 note.file.name = request.data.get('file_path')
            note.save()
            return Response({"id": str(note.id)}, status=status.HTTP_201_CREATED)
        except Project.DoesNotExist:
            return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

class ProjectNoteDetailView(APIView):
    def patch(self, request, note_id):
        try:
            note = ProjectNote.objects.get(id=note_id)
            note.title = request.data.get('title', note.title)
            note.content = request.data.get('content', note.content)
            if 'file_url' in request.data:
                note.file.name = request.data.get('file_url')
            elif 'file_path' in request.data:
                note.file.name = request.data.get('file_path')
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
