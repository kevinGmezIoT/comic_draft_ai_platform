import copy
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from langsmith import traceable

from ..adapters import get_image_adapter
from ..models import AgentState
from ..prompts import PromptBuilder
from ..supervisor import ContinuitySupervisor
from ..telemetry import submit_with_current_context, timed_function, timed_step


@timed_function("node.image_generator")
def image_generator(state: AgentState):
    print("--- AGENT F & H: MULTIMODAL IMAGE GENERATION ---")
    prompt_builder = PromptBuilder(state["project_id"])
    continuity_supervisor = ContinuitySupervisor(state["project_id"])

    continuity = state.get("continuity_state", {})
    sorted_panels = sorted(state["panels"], key=lambda x: (x.get("page_number", 1), x.get("order_in_page", 0)))

    character_manager = prompt_builder.cm
    scenery_manager = prompt_builder.scm

    target_panel_id = str(state.get("panel_id")) if state.get("panel_id") else None
    panel_purposes = state.get("panel_purposes", {})
    enable_parallel_generator = os.getenv("ENABLE_PARALLEL_GENERATOR", "0").strip().lower() not in {"0", "false", "no", "off"}
    max_generator_workers = max(1, int(os.getenv("GENERATOR_CONCURRENCY", "2")))

    updated_panel_map = {}
    panel_jobs = []

    for panel in sorted_panels:
        panel_id = str(panel.get("id"))

        if state.get("action") == "regenerate_panel" and target_panel_id and panel_id != target_panel_id:
            updated_panel_map[panel_id] = panel
            continue

        is_target = state.get("action") == "regenerate_panel" and panel_id == target_panel_id

        if panel.get("image_url") and panel.get("status") not in ["pending", "editing"] and not is_target:
            updated_panel_map[panel_id] = panel
            continue

        with timed_step(f"image_generator.continuity[{panel.get('id')}]"):
            continuity = continuity_supervisor.update_state(continuity, panel)

        panel_jobs.append(
            {
                "panel": copy.deepcopy(panel),
                "continuity": copy.deepcopy(continuity),
                "is_target": is_target,
            }
        )

    print(f"DEBUG: [ImageGenerator] Pending panel jobs: {len(panel_jobs)}")

    @traceable(name="image_generator_panel_job", project_name=os.getenv("LANGCHAIN_PROJECT", "comic-draft-ai"))
    def resolve_panel_job(job, adapter_override=None):
        panel = copy.deepcopy(job["panel"])
        panel_id = panel.get("id")
        is_target = job["is_target"]
        panel_continuity = copy.deepcopy(job["continuity"])
        panel_adapter = adapter_override or get_image_adapter()

        with timed_step(f"image_generator.prompt_build[{panel_id}]"):
            augmented_prompt = prompt_builder.build_panel_prompt(panel, state["world_model_summary"], panel_continuity)

        page_num = panel.get("page_number", 1)
        order = panel.get("order_in_page", 0)
        purpose_key = f"page_{page_num}_panel_{order + 1}"
        panel_purpose = panel_purposes.get(purpose_key, "")
        if panel_purpose:
            augmented_prompt = f"NARRATIVE PURPOSE: {panel_purpose}\n\n{augmented_prompt}"
            print(f"DEBUG: [StoryUnderstanding -> Generator] Panel {panel_id} enriched with purpose: {panel_purpose[:80]}...")

        current_img = None
        if is_target:
            current_img = state.get("current_image_url")
        else:
            current_img = panel.get("current_image_url") or panel.get("image_url")

        context_images = []
        char_source_list = panel.get("character_refs") or panel.get("characters", [])
        for char_name in char_source_list:
            char_refs = character_manager.get_character_images(char_name)
            if char_refs:
                context_images.extend(char_refs)

        scene_source_list = panel.get("scenery_refs") or ([panel.get("scenery")] if panel.get("scenery") else [])
        for scene_name in scene_source_list:
            scene_refs = scenery_manager.get_scenery_images(scene_name)
            if scene_refs:
                context_images.extend(scene_refs)

        ref_img = state.get("reference_image_url") if is_target else None
        if not ref_img:
            ref_img = panel.get("reference_image_url")
        if ref_img:
            context_images.append(ref_img)

        seen = set()
        unique_context = [x for x in context_images if not (x in seen or seen.add(x))]

        print(f"DEBUG: Panel {panel_id} Context Images ({len(unique_context)}): {unique_context}")
        print(f"DEBUG: Augmented Prompt: {augmented_prompt[:150]}...")
        print(f"DEBUG: Style Prompt: {panel.get('panel_style')}")

        layout = panel.get("layout", {"w": 50, "h": 50})
        w, h = layout.get("w", 50), layout.get("h", 50)
        aspect_ratio = "1:1"
        if w / h > 1.2:
            aspect_ratio = "16:9"
        elif h / w > 1.2:
            aspect_ratio = "9:16"

        init_image = current_img
        if not is_target and not init_image and panel.get("status") == "editing" and panel.get("image_url"):
            init_image = panel.get("image_url")

        if init_image:
            print(f"DEBUG: I2I/Editing panel {panel_id} using init_image: {init_image}")
            with timed_step(f"image_generator.render_edit[{panel_id}]"):
                url = panel_adapter.edit_image(
                    original_image_url=init_image,
                    prompt=augmented_prompt,
                    style_prompt=panel.get("panel_style"),
                    context_images=unique_context,
                )
        else:
            with timed_step(f"image_generator.render_new[{panel_id}]"):
                url = panel_adapter.generate_panel(
                    augmented_prompt,
                    style_prompt=panel.get("panel_style"),
                    aspect_ratio=aspect_ratio,
                    context_images=unique_context,
                )

        panel["image_url"] = url
        panel["status"] = "generated"
        panel["prompt"] = augmented_prompt
        return panel

    resolved_panel_map = {}
    if enable_parallel_generator and len(panel_jobs) > 1 and max_generator_workers > 1:
        worker_count = min(max_generator_workers, len(panel_jobs))
        print(f"DEBUG: [ImageGenerator] Parallel panel generation enabled with {worker_count} workers.")
        with timed_step("image_generator.parallel_panels"):
            with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="panel-gen") as executor:
                future_map = {
                    submit_with_current_context(executor, resolve_panel_job, job): str(job["panel"].get("id"))
                    for job in panel_jobs
                }
                for future in as_completed(future_map):
                    resolved_panel = future.result()
                    resolved_panel_map[str(resolved_panel.get("id"))] = resolved_panel
    else:
        print("DEBUG: [ImageGenerator] Using sequential panel rendering.")
        shared_adapter = get_image_adapter()
        for job in panel_jobs:
            resolved_panel = resolve_panel_job(job, shared_adapter)
            resolved_panel_map[str(resolved_panel.get("id"))] = resolved_panel

    updated_panel_map.update(resolved_panel_map)
    updated_panels = [updated_panel_map.get(str(panel.get("id")), panel) for panel in sorted_panels]

    return {"panels": updated_panels, "continuity_state": continuity, "current_step": "balloons"}
