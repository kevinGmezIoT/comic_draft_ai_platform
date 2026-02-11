from .models import Project, Page, Panel

def process_agent_result(project_id, data):
    """
    Processes the result from the agent (can be from SQS or HTTP callback).
    """
    print(f"DEBUG: [PROCESSOR] Processing result for project {project_id}")
    
    try:
        project = Project.objects.get(id=project_id)
        status_received = data.get('status')
        print(f"DEBUG: [PROCESSOR] Status: {status_received}")
        
        if status_received == 'failed':
            error_msg = data.get('error', 'Unknown Error')
            project.status = 'failed'
            project.last_error = error_msg
            project.save()
            return {"status": "error_logged"}

        result = data.get('result', {})
        panels_data = result.get('panels', [])
        
        if not panels_data:
            project.status = 'failed'
            project.last_error = "El Agente no pudo generar una maquetación válida (0 paneles)."
            project.save()
            return {"status": "no_panels_found"}

        # Page and Panel reconciliation logic
        pages_map = {}
        processed_panel_ids = []
        
        for p_data in panels_data:
            p_num = p_data.get('page_number', 1)
            if p_num not in pages_map:
                page, _ = Page.objects.get_or_create(project=project, page_number=p_num)
                pages_map[p_num] = page
            
            panel_id = p_data.get('id')
            panel = None
            
            # Smart ID matching (UUID or Int)
            if panel_id:
                panel_id_str = str(panel_id)
                if len(panel_id_str) > 30: # Likely UUID
                    panel = Panel.objects.filter(id=panel_id_str).first()
                elif panel_id_str.isdigit(): # Likely serial ID (Int)
                    panel = Panel.objects.filter(id=int(panel_id_str)).first()
            
            if not panel:
                # Fallback to page/order matching if ID not found or not provided
                panel, created = Panel.objects.update_or_create(
                    page=pages_map[p_num],
                    order=p_data.get('order_in_page', 0),
                    defaults={
                        "prompt": p_data.get('prompt', 'Cinematic comic panel'),
                        "scene_description": p_data.get('scene_description', ''),
                        "balloons": p_data.get('balloons', []),
                        "layout": p_data.get('layout', {}),
                        "status": "completed"
                    }
                )
            else:
                # Update found panel
                # PRESERVE existing prompt if the new one is empty or the placeholder
                new_prompt = p_data.get('prompt')
                if new_prompt and "placeholder" not in new_prompt.lower():
                    panel.prompt = new_prompt
                
                panel.scene_description = p_data.get('scene_description', panel.scene_description)
                panel.balloons = p_data.get('balloons', [])
                panel.layout = p_data.get('layout', panel.layout)
                panel.status = "completed"
                panel.order = p_data.get('order_in_page', panel.order)
                panel.save()
            
            processed_panel_ids.append(panel.id)
            
            if p_data.get('image_url'):
                panel.image.name = p_data['image_url']
                panel.save()

        # Reconcile Panels
        for p_num, page in pages_map.items():
            page.panels.exclude(id__in=processed_panel_ids).delete()
        
        # Reconcile Pages
        project.pages.exclude(page_number__in=pages_map.keys()).delete()
        
        # Merged Pages
        merged_pages_data = result.get('merged_pages', [])
        for m_data in merged_pages_data:
            p_num = m_data.get('page_number')
            page = Page.objects.filter(project=project, page_number=p_num).first()
            if page:
                image_url = m_data.get('image_url', '')
                if image_url:
                    page.merged_image.name = image_url
                page.save()

        project.status = 'completed'
        project.last_error = None
        project.save()
        print(f"DEBUG: [PROCESSOR] Project {project_id} updated successfully.")
        return {"status": "success"}

    except Project.DoesNotExist:
        print(f"ERROR: [PROCESSOR] Project {project_id} not found.")
        return {"status": "project_not_found"}
    except Exception as e:
        print(f"ERROR: [PROCESSOR] Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}
