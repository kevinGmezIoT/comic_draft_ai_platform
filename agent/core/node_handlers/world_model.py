import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List

from langchain_openai import ChatOpenAI
from langsmith import traceable

from ..knowledge import CanonicalStore, CharacterManager, SceneryManager
from ..models import AgentState
from ..telemetry import submit_with_current_context, timed_function, timed_step


@timed_function("node.world_model_builder")
def world_model_builder(state: AgentState):
    print("--- WORLD MODEL BUILDING (Characters & Scenarios) ---")
    canon = CanonicalStore(state["project_id"])
    batch_canon_save = os.getenv("ENABLE_BATCH_CANON_SAVE", "1").strip().lower() not in {"0", "false", "no", "off"}
    if batch_canon_save:
        canon.autosave = False
    cm = CharacterManager(state["project_id"], canon=canon)
    scm = SceneryManager(state["project_id"], canon=canon)
    llm = ChatOpenAI(model=os.getenv("OPENAI_MODEL_ID"), temperature=0)

    backend_chars = state.get("global_context", {}).get("characters", [])
    backend_scenes = state.get("global_context", {}).get("sceneries", [])

    known_character_images = {
        c["name"].lower(): c.get("image_urls", [c["image_url"]] if c.get("image_url") else [])
        for c in backend_chars
    }
    known_scenery_images = {
        s["name"].lower(): s.get("image_urls", [s["image_url"]] if s.get("image_url") else [])
        for s in backend_scenes
    }
    enable_parallel_world_traits = (
        os.getenv("ENABLE_PARALLEL_WORLD_TRAITS", "1").strip().lower() not in {"0", "false", "no", "off"}
    )
    max_world_trait_workers = max(1, int(os.getenv("WORLD_TRAITS_CONCURRENCY", "2")))
    force_world_traits_refresh = os.getenv("FORCE_WORLD_TRAITS_REFRESH", "0").strip().lower() in {"1", "true", "yes", "on"}
    pending_trait_jobs = {}

    def queue_trait_job(kind: str, name: str, image_urls: List[str]):
        unique_images = []
        for image_url in image_urls or []:
            if image_url and image_url not in unique_images:
                unique_images.append(image_url)
        if not unique_images:
            return

        key = (kind, name.lower())
        if key not in pending_trait_jobs:
            pending_trait_jobs[key] = {
                "kind": kind,
                "name": name,
                "image_urls": unique_images,
            }
            return

        for image_url in unique_images:
            if image_url not in pending_trait_jobs[key]["image_urls"]:
                pending_trait_jobs[key]["image_urls"].append(image_url)

    for b_char in backend_chars:
        name = b_char["name"]
        description = b_char.get("description", "")
        img_urls = b_char.get("image_urls", [b_char["image_url"]] if b_char.get("image_url") else [])
        should_extract = cm.register_character(name, description, img_urls, extract_traits=False, force_extract=force_world_traits_refresh)
        if should_extract:
            queue_trait_job("character", name, img_urls)
        else:
            print(f"DEBUG: [WorldModelBuilder] Skipping traits for character '{name}' (already present and force disabled).")
        print(f"DEBUG: [Wizard Asset] Character '{name}' registered from backend with {len(img_urls)} images.")

    for b_scene in backend_scenes:
        name = b_scene["name"]
        description = b_scene.get("description", "")
        img_urls = b_scene.get("image_urls", [b_scene["image_url"]] if b_scene.get("image_url") else [])
        should_extract = scm.register_scenery(name, description, img_urls, extract_traits=False, force_extract=force_world_traits_refresh)
        if should_extract:
            queue_trait_job("scenery", name, img_urls)
        else:
            print(f"DEBUG: [WorldModelBuilder] Skipping traits for scenery '{name}' (already present and force disabled).")
        print(f"DEBUG: [Wizard Asset] Scenery '{name}' registered from backend with {len(img_urls)} images.")

    existing_chars = list(cm.canon.data.get("characters", {}).keys())
    existing_scenes = list(scm.canon.data.get("sceneries", {}).keys())
    original_names_map = cm.canon.data.get("metadata", {}).get("original_keys", {})

    display_chars = [original_names_map.get(k, k) for k in existing_chars]
    display_scenes = [original_names_map.get(k, k) for k in existing_scenes]

    prompt = f"""
    BasÃ¡ndote en este resumen del mundo, identifica a los personajes principales y los escenarios clave.
    
    RESUMEN:
    {state['world_model_summary']}
    
    ACTIVOS YA REGISTRADOS (USA ESTOS NOMBRES EXACTOS SI COINCIDEN O DESCRÃBELOS MEJOR):
    - Personajes: {', '.join(display_chars) if display_chars else "Ninguno"}
    - Escenarios: {', '.join(display_scenes) if display_scenes else "Ninguno"}
    
    IMÃGENES DE REFERENCIA DISPONIBLES (archivos): {", ".join([os.path.basename(p) for p in state.get("reference_images", [])])}
    
    Responde en formato JSON:
    {{
        "characters": [{{"name": "nombre (Respetar nombres ya listados)", "description": "..."}}],
        "sceneries": [{{"name": "nombre (Respetar nombres ya listados)", "description": "descripciÃ³n visual detallada"}}]
    }}
    """
    traits_applied = False

    try:
        with timed_step("world_model_builder.llm_invoke"):
            response = llm.invoke(prompt)
        content = response.content.strip()
        if content.startswith("```json"):
            content = content[7:-3].strip()
        data = json.loads(content)

        ref_images = state.get("reference_images", [])

        for char in data.get("characters", []):
            name = char["name"]
            description = char["description"]
            images = []

            name_canon, existing_char = cm._find_character(name)
            target_name = name_canon if name_canon else name

            if existing_char:
                images = existing_char.get("ref_images", [])

            for b_name, b_urls in known_character_images.items():
                if target_name.lower() in b_name or b_name in target_name.lower():
                    for url in b_urls:
                        if url and url not in images:
                            images.append(url)
                    break

            if not images:
                for p in ref_images:
                    clean_name = target_name.lower().replace(" ", "").replace("_", "")
                    clean_path = os.path.basename(p).lower().replace(" ", "").replace("_", "")
                    if clean_name in clean_path:
                        images.append(p)
                        break

            dedup_images = list(set(images))
            should_extract = cm.register_character(
                target_name,
                description,
                dedup_images,
                extract_traits=False,
                force_extract=force_world_traits_refresh,
            )
            if should_extract:
                queue_trait_job("character", target_name, dedup_images)
            elif dedup_images:
                print(
                    f"DEBUG: [WorldModelBuilder] Skipping traits for character '{target_name}' "
                    f"(already present and force disabled)."
                )

        for scene in data.get("sceneries", []):
            name = scene["name"]
            description = scene["description"]
            images = []

            name_canon, existing_scene = scm._find_scenery(name)
            target_name = name_canon if name_canon else name

            if existing_scene:
                images = existing_scene.get("ref_images", [])

            for b_name, b_urls in known_scenery_images.items():
                if target_name.lower() in b_name or b_name in target_name.lower():
                    for url in b_urls:
                        if url and url not in images:
                            images.append(url)
                    print(f"DEBUG: Scenery '{target_name}' matched with backend scenery '{b_name}' ({len(b_urls)} images)")
                    break

            if not images:
                for p in ref_images:
                    clean_name = target_name.lower().replace(" ", "").replace("_", "")
                    clean_path = os.path.basename(p).lower().replace(" ", "").replace("_", "")
                    if clean_name in clean_path:
                        images.append(p)
                        print(f"DEBUG: Scenery '{target_name}' matched by name in file '{p}'")
                        break

            dedup_images = list(set(images))
            should_extract = scm.register_scenery(
                target_name,
                description,
                dedup_images,
                extract_traits=False,
                force_extract=force_world_traits_refresh,
            )
            if should_extract:
                queue_trait_job("scenery", target_name, dedup_images)
            elif dedup_images:
                print(
                    f"DEBUG: [WorldModelBuilder] Skipping traits for scenery '{target_name}' "
                    f"(already present and force disabled)."
                )
            print(f"Registered scenery: {target_name} with {len(dedup_images)} images.")

        if pending_trait_jobs:
            print(f"DEBUG: [WorldModelBuilder] Pending trait jobs: {len(pending_trait_jobs)}")

            @traceable(name="world_model_trait_job", project_name=os.getenv("LANGCHAIN_PROJECT", "comic-draft-ai"))
            def resolve_trait_job(job: Dict[str, object]) -> Dict[str, object]:
                try:
                    if job["kind"] == "character":
                        traits = cm.analyze_visual_traits(job["name"], job["image_urls"])
                    else:
                        traits = scm.analyze_visual_traits(job["name"], job["image_urls"])
                    return {**job, "traits": traits}
                except Exception as trait_error:
                    print(f"WARNING: Trait job failed for {job['kind']} '{job['name']}': {trait_error}")
                    return {**job, "traits": None}

            resolved_trait_jobs = []
            trait_jobs = list(pending_trait_jobs.values())

            if enable_parallel_world_traits and len(trait_jobs) > 1 and max_world_trait_workers > 1:
                worker_count = min(max_world_trait_workers, len(trait_jobs))
                print(f"DEBUG: [WorldModelBuilder] Parallel trait extraction enabled with {worker_count} workers.")
                with timed_step("world_model_builder.parallel_traits"):
                    with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="world-traits") as executor:
                        futures = [submit_with_current_context(executor, resolve_trait_job, job) for job in trait_jobs]
                        for future in as_completed(futures):
                            resolved_trait_jobs.append(future.result())
            else:
                print("DEBUG: [WorldModelBuilder] Using sequential trait extraction.")
                for job in trait_jobs:
                    resolved_trait_jobs.append(resolve_trait_job(job))

            for job in resolved_trait_jobs:
                traits = job.get("traits")
                if traits is None:
                    continue
                if job["kind"] == "character":
                    canon.update_character(job["name"], {"visual_traits": traits})
                else:
                    canon.update_scenery(job["name"], {"visual_traits": traits})
            traits_applied = True

    except Exception as e:
        print(f"Error extracting world elements: {e}")
    finally:
        if pending_trait_jobs and not traits_applied:
            print("DEBUG: [WorldModelBuilder] Applying pending trait jobs in fallback mode.")
            for job in pending_trait_jobs.values():
                try:
                    if job["kind"] == "character":
                        traits = cm.analyze_visual_traits(job["name"], job["image_urls"])
                        canon.update_character(job["name"], {"visual_traits": traits})
                    else:
                        traits = scm.analyze_visual_traits(job["name"], job["image_urls"])
                        canon.update_scenery(job["name"], {"visual_traits": traits})
                except Exception as trait_error:
                    print(f"WARNING: Fallback trait job failed for {job['kind']} '{job['name']}': {trait_error}")
        if batch_canon_save:
            canon.autosave = True
            canon.flush()

    return {"current_step": "planner", "continuity_state": {}, "canvas_dimensions": "800x1100 (A4)"}
