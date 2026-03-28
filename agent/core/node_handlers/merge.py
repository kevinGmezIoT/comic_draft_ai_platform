import base64
import os

from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from ..adapters import get_image_adapter
from ..models import AgentState
from ..telemetry import timed_function, timed_step


@timed_function("node.page_merger")
def page_merger(state: AgentState):
    print("--- ORGANIC PAGE MERGE (Image-to-Image with Composite & Balloons) ---")
    from core.utils import PageRenderer

    adapter = get_image_adapter()
    renderer = PageRenderer()

    pages = {}
    target_page = state.get("page_number")
    print(f"DEBUG: Target page: {target_page}")

    sorted_panels = sorted(state["panels"], key=lambda x: (int(x.get("page_number", 0)), int(x.get("order_in_page", 0))))

    for p in sorted_panels:
        p_num = p["page_number"]
        if target_page and int(p_num) != int(target_page):
            print(f"DEBUG: Skipping panel {p_num} for page {target_page}")
            continue
        if p_num not in pages:
            pages[p_num] = []
        print(f"DEBUG: Adding panel {p_num} to page {p_num}")
        pages[p_num].append(p)

    merged_results = state.get("merged_pages", [])
    if target_page:
        merged_results = [m for m in merged_results if int(m["page_number"]) != int(target_page)]

    last_page_s3_key = None
    sorted_page_nums = sorted(pages.keys(), key=int)
    print(sorted_page_nums)
    for page_num in sorted_page_nums:
        panel_list = pages[page_num]
        print(f"Merging Page {page_num}...")

        with timed_step(f"page_merger.composite[{page_num}]"):
            composite_path = renderer.create_composite_page(panel_list, include_balloons=True)

        with open(composite_path, "rb") as f:
            composite_b64 = base64.b64encode(f.read()).decode("utf-8")

        vision_prompt = (
            "Esta es una maqueta de una pÃ¡gina de cÃ³mic con paneles y globos. "
            "Describe cÃ³mo deberÃ­an mezclarse los fondos de manera artÃ­stica y orgÃ¡nica "
            "para que parezca una sola ilustraciÃ³n fluida, manteniendo la posiciÃ³n "
            "de los personajes y globos."
        )

        def get_visual_blend_description(b64_image, prompt):
            models_to_try = [
                ("google", os.getenv("GEMINI_MODEL_ID_TEXT")),
                ("openai", os.getenv("OPENAI_MODEL_ID")),
            ]

            last_error = None
            for provider, model_name in models_to_try:
                try:
                    print(f"DEBUG: Attempting visual analysis with {model_name}...")
                    if provider == "google":
                        llm = ChatGoogleGenerativeAI(model=model_name, temperature=0.2)
                    else:
                        llm = ChatOpenAI(model=model_name, temperature=0.2)

                    message = HumanMessage(
                        content=[
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_image}"}},
                        ]
                    )
                    response = llm.invoke([message])
                    return response.content
                except Exception as e:
                    print(f"WARNING: Model {model_name} failed: {e}")
                    last_error = e
                    continue

            print(f"ERROR: All models failed for vision analysis. Fallback to default prompt. Last error: {last_error}")
            return "Blend the backgrounds smoothly."

        with timed_step(f"page_merger.visual_analysis[{page_num}]"):
            visual_blend_description = get_visual_blend_description(composite_b64, vision_prompt)
        print(f"Visual Blend Insight: {visual_blend_description[:100]}...")

        user_instr = state.get("instructions", "")
        instr_part = f"\nUSER INSTRUCTIONS TO CHANGE FROM ORIGINAL IMAGE: {user_instr}" if user_instr else ""

        page_summaries = state.get("page_summaries", {})
        page_summary = page_summaries.get(int(page_num), page_summaries.get(str(page_num), ""))
        summary_part = f"\nPAGE NARRATIVE CONTEXT: {page_summary}" if page_summary else ""
        if page_summary:
            print(f"DEBUG: [StoryUnderstanding -> Merger] Page {page_num} enriched with summary: {page_summary[:100]}...")

        merge_prompt = (
            f"ORGANIC COMIC PAGE MERGE. \nInstrucciones visuales: {visual_blend_description} "
            f"{instr_part}{summary_part} \nPÃ¡gina en el guiÃ³n: {page_num}\n"
            f"Style: {state.get('style_guide', '')}. Professional comic art style."
        )

        merge_context_images = []
        bucket = os.getenv("AWS_STORAGE_BUCKET_NAME")

        if last_page_s3_key:
            prev_s3_uri = f"s3://{bucket}/{last_page_s3_key}"
            print(f"DEBUG: Adding previous page (PÃ¡g {int(page_num)-1}) as continuity context: {prev_s3_uri}")
            merge_context_images.append(prev_s3_uri)

        try:
            print(f"DEBUG: [PageMerger] Sending Page {page_num} to provider for organic blend...")
            with timed_step(f"page_merger.render[{page_num}]"):
                raw_merged_s3_key = adapter.generate_page_merge(
                    merge_prompt,
                    style_prompt=state.get("style_guide", ""),
                    init_image_path=composite_path,
                    context_images=merge_context_images,
                )

            last_page_s3_key = raw_merged_s3_key
            merged_results.append({"page_number": page_num, "image_url": raw_merged_s3_key})
            print(f"DEBUG: [PageMerger] Page {page_num} merge completed. Result S3 Key: {raw_merged_s3_key}")

        except Exception as e:
            print(f"ERROR: [PageMerger] Failed to merge Page {page_num}: {e}")
            raise e

        finally:
            if os.path.exists(composite_path):
                try:
                    os.remove(composite_path)
                except Exception:
                    pass
            if "tmp_raw_path" in locals() and os.path.exists(tmp_raw_path):
                try:
                    os.remove(tmp_raw_path)
                except Exception:
                    pass
            if "final_composite_local_path" in locals() and os.path.exists(final_composite_local_path):
                try:
                    os.remove(final_composite_local_path)
                except Exception:
                    pass

    return {"merged_pages": merged_results, "panels": state["panels"], "current_step": "done"}
