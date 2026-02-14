from .models import Project, Page, Panel

def process_agent_result(project_id, data):
    """
    Processes the result from the agent (can be from SQS or HTTP callback).
    """
    print(f"DEBUG: [PROCESSOR] Processing result for project {project_id}")
    
    try:
        project = Project.objects.get(id=project_id)
        status_received = data.get('status')
        action = data.get('action', 'NOT_FOUND')
        print(f"DEBUG: [PROCESSOR] Processing Project {project_id} | Status: {status_received} | Action: {action}")
        
        if status_received == 'failed':
            error_msg = data.get('error', 'Unknown Error')
            project.status = 'failed'
            project.last_error = error_msg
            project.save()
            return {"status": "error_logged"}

        result = data.get('result', {})
        panels_data = result.get('panels', [])
        print(f"DEBUG: [PROCESSOR] Panels in payload: {len(panels_data)}")
        
        if not panels_data:
            project.status = 'failed'
            project.last_error = "El Agente no pudo generar una maquetación válida (0 paneles)."
            project.save()
            return {"status": "no_panels_found"}

        # Page and Panel reconciliation logic
        pages_map = {}
        processed_panel_ids = []
        
        for p_data in panels_data:
            p_num = int(p_data.get('page_number', 1))
            if p_num not in pages_map:
                page, created_page = Page.objects.get_or_create(project=project, page_number=p_num)
                pages_map[p_num] = page
                if created_page:
                    print(f"DEBUG: [PROCESSOR] Created NEW Page {p_num}")
            
            panel_id = p_data.get('id')
            panel = None
            
            # Smart ID matching (UUID or Int)
            if panel_id:
                panel_id_str = str(panel_id)
                if len(panel_id_str) > 30: # Likely UUID
                    panel = Panel.objects.filter(id=panel_id_str, page__project=project).first()
                elif panel_id_str.isdigit(): # Likely serial ID (Int)
                    panel = Panel.objects.filter(id=int(panel_id_str), page__project=project).first()
            
            if panel:
                print(f"DEBUG: [PROCESSOR] Matched Panel ID {panel.id} (Page {panel.page.page_number})")
            
            if not panel:
                # Fallback to page/order matching
                order_val = int(p_data.get('order_in_page', 0))
                panel, created = Panel.objects.update_or_create(
                    page=pages_map[p_num],
                    order=order_val,
                    defaults={
                        "prompt": p_data.get('prompt', 'Cinematic comic panel'),
                        "scene_description": p_data.get('scene_description', ''),
                        "balloons": p_data.get('balloons', []),
                        "layout": p_data.get('layout', {}),
                        "status": "completed"
                    }
                )
                if created:
                    print(f"DEBUG: [PROCESSOR] Created NEW Panel at Page {p_num}, Order {order_val}")
                else:
                    print(f"DEBUG: [PROCESSOR] Updated existing Panel by Page/Order at Page {p_num}, Order {order_val}")
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
            
            # Reconcile Image: Only update if it's a full generation OR if this is the target panel of a regeneration
            # This prevents mirroring back absolute URLs into the FileField name for unchanged panels
            should_update_image = (action == 'generate' or action == 'NOT_FOUND') or (action == 'regenerate_panel' and str(panel.id) == str(data.get('panel_id')))

            if p_data.get('image_url') and should_update_image:
                raw_url = p_data['image_url'].split('?')[0]
                # If it's a full URL (contains http), try to extract only the path after the bucket
                # This protects against accidental corruption if the agent echoes back a full URL
                if "http" in raw_url:
                    parts = raw_url.split('/')
                    if "projects" in parts:
                        idx = parts.index("projects")
                        clean_url = "/".join(parts[idx:])
                    else:
                        clean_url = raw_url # Fallback
                else:
                    clean_url = raw_url
                
                panel.image.name = clean_url
                panel.save()
                print(f"DEBUG: [PROCESSOR] Saved Image for Panel {panel.id}: {clean_url}")
            elif p_data.get('image_url'):
                print(f"DEBUG: [PROCESSOR] Skipping image update for Panel {panel.id} (Action: {action})")

        # Reconcile Panels/Pages ONLY for full generation
        # Specialized actions (regenerate_panel, regenerate_merge) should only update, not delete.
        if action == 'generate' or action == 'NOT_FOUND':
            print(f"DEBUG: [PROCESSOR] Running reconciliation (action={action}). Deleting unmatched panels/pages.")
            # Reconcile Panels
            for p_num, page in pages_map.items():
                deleted_count = page.panels.exclude(id__in=processed_panel_ids).count()
                print(f"DEBUG: [PROCESSOR] Deleting {deleted_count} panels from Page {p_num}")
                page.panels.exclude(id__in=processed_panel_ids).delete()
            
            # Reconcile Pages
            deleted_pages = project.pages.exclude(page_number__in=pages_map.keys()).count()
            print(f"DEBUG: [PROCESSOR] Deleting {deleted_pages} pages")
            project.pages.exclude(page_number__in=pages_map.keys()).delete()
        else:
            print(f"DEBUG: [PROCESSOR] SAFE MODE: Skipping deletions for action: {action}")
        
        # Merged Pages
        merged_pages_data = result.get('merged_pages', [])
        for m_data in merged_pages_data:
            p_num = m_data.get('page_number')
            page = Page.objects.filter(project=project, page_number=p_num).first()
            if page:
                image_url = m_data.get('image_url', '')
                if image_url:
                    clean_url = image_url.split('?')[0]
                    page.merged_image.name = clean_url
                page.save()
                print(f"DEBUG: [PROCESSOR] Saved Merged Image for Page {p_num}: {clean_url}")

        project.status = 'completed'
        project.last_error = None
        project.save()
        
        final_pages = project.pages.count()
        final_panels = Panel.objects.filter(page__project=project).count()
        print(f"DEBUG: [PROCESSOR] Summary: {final_pages} Pages, {final_panels} Panels total. Status set to COMPLETED.")
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
