from .models import Project, Page, Panel, Character, Scenery

def process_agent_result(project_id, data):
    """
    Processes the result from the agent (can be from SQS or HTTP callback).
    """
    
    try:
        project = Project.objects.get(id=project_id)
        status_received = data.get('status')
        action = data.get('action', 'NOT_FOUND')
        
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
            p_num = int(p_data.get('page_number', 1))
            if p_num not in pages_map:
                page, created_page = Page.objects.get_or_create(project=project, page_number=p_num)
                pages_map[p_num] = page
            
            panel_id = p_data.get('id')
            panel = None
            
            # Smart ID matching (UUID or Int)
            if panel_id:
                panel_id_str = str(panel_id)
                if len(panel_id_str) > 30: # Likely UUID
                    panel = Panel.objects.filter(id=panel_id_str, page__project=project).first()
                elif panel_id_str.isdigit(): # Likely serial ID (Int)
                    panel = Panel.objects.filter(id=int(panel_id_str), page__project=project).first()                        
            if not panel:
                # ONLY create new panels during a full generation or if explicitly missing.
                # During 'regenerate_panel', we should NOT be re-creating panels by order fallback.
                if action == 'regenerate_panel':
                    continue

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
                        "character_refs": p_data.get('characters', []),
                        "scenery_refs": p_data.get('sceneries') or ([p_data.get('scenery')] if p_data.get('scenery') else []),
                        "status": "completed"
                    }
                )
            else:
                # Update found panel
                
                # CRITICAL: For specialized actions (like regenerate_panel), ONLY update if it's the target.
                # Otherwise, the agent context might overwrite valid user modifications on other panels.
                is_target = True
                if action == 'regenerate_panel':
                    target_pid = data.get('panel_id') or result.get('panel_id')
                    is_target = str(panel.id) == str(target_pid)
                elif action == 'regenerate_merge':
                    is_target = False # Merges shouldn't touch panels
                
                if not is_target:
                    processed_panel_ids.append(panel.id)
                    continue

                # PRESERVE existing prompt if the new one is empty or the placeholder
                new_prompt = p_data.get('prompt')
                if new_prompt and "placeholder" not in new_prompt.lower():
                    panel.prompt = new_prompt
                
                panel.scene_description = p_data.get('scene_description', panel.scene_description)
                
                # ENHANCED BALLOON MERGE: Match by content to preserve interactive props
                new_balloons_list = p_data.get('balloons')
                if new_balloons_list is not None:
                    existing_balloons = panel.balloons or []
                    eb_map = {}
                    for eb in existing_balloons:
                        key = f"{eb.get('character', '')}:{eb.get('text', '')[:30]}".lower().strip()
                        eb_map[key] = eb

                    merged = []
                    for nb in new_balloons_list:
                        nb_key = f"{nb.get('character', '')}:{nb.get('text', '')[:30]}".lower().strip()
                        if nb_key in eb_map:
                            eb = eb_map[nb_key]
                            for prop in ('x', 'y', 'width', 'height', 'fontSize'):
                                if prop in eb and prop not in nb:
                                    nb[prop] = eb[prop]
                        merged.append(nb)
                    panel.balloons = merged
                
                panel.layout = p_data.get('layout', panel.layout)
                panel.status = "completed"
                panel.order = p_data.get('order_in_page', panel.order)
                # Persist character assignments from the planner so they survive regeneration
                if p_data.get('characters'):
                    panel.character_refs = p_data['characters']
                if p_data.get('sceneries') or p_data.get('scenery'):
                    panel.scenery_refs = p_data.get('sceneries') or [p_data.get('scenery')]
                panel.save()
            
            processed_panel_ids.append(panel.id)
            
            # Reconcile Image: Only update if it's a full generation OR if this is the target panel of a regeneration
            # This prevents mirroring back absolute URLs into the FileField name for unchanged panels
            should_update_image = (action == 'generate' or action == 'NOT_FOUND') or (action == 'regenerate_panel' and str(panel.id) == str(data.get('panel_id') or result.get('panel_id')))

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

        # Reconcile Panels/Pages ONLY for full generation
        # Specialized actions (regenerate_panel, regenerate_merge) should only update, not delete.
        if action == 'generate' or action == 'NOT_FOUND':
            # Reconcile Panels
            for p_num, page in pages_map.items():
                deleted_count = page.panels.exclude(id__in=processed_panel_ids).count()
                page.panels.exclude(id__in=processed_panel_ids).delete()
            
            # Reconcile Pages
            deleted_pages = project.pages.exclude(page_number__in=pages_map.keys()).count()
            project.pages.exclude(page_number__in=pages_map.keys()).delete()
        
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

        # Character & Scenery Synchronization (Canon)
        characters_data = result.get('characters', [])
        for c_data in characters_data:
            name = c_data.get('name')
            if name:
                Character.objects.update_or_create(
                    project=project,
                    name=name,
                    defaults={
                        "description": c_data.get('description', ''),
                        "metadata": c_data.get('metadata', c_data.get('visual_traits', {}))
                    }
                )

        sceneries_data = result.get('sceneries', [])
        for s_data in sceneries_data:
            name = s_data.get('name')
            if name:
                Scenery.objects.update_or_create(
                    project=project,
                    name=name,
                    defaults={
                        "description": s_data.get('description', ''),
                        "metadata": s_data.get('metadata', s_data.get('visual_traits', {}))
                    }
                )

        project.status = 'completed'
        project.last_error = None
        # Persist world model summary for successive merges/regenerations
        if result.get('world_model_summary'):
            project.world_model_summary = result['world_model_summary']
        project.save()
        
        final_pages = project.pages.count()
        final_panels = Panel.objects.filter(page__project=project).count()
        return {"status": "success"}

    except Project.DoesNotExist:
        return {"status": "project_not_found"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}
