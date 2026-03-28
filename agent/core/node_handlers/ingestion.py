import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from ..knowledge import KnowledgeManager, StyleManager
from ..models import AgentState
from ..telemetry import submit_with_current_context, timed_function, timed_step


@timed_function("node.ingest_and_rag")
def ingest_and_rag(state: AgentState):
    print("--- RAG & INGESTION ---")
    km = KnowledgeManager(state["project_id"])
    vectorstore, image_paths = km.ingest_from_urls(state["sources"])

    global_ctx = state.get("global_context", {})
    summary_parts = []

    if global_ctx.get("description"):
        summary_parts.append(f"SYNOPSIS / DESCRIPTION: {global_ctx['description']}")
    if global_ctx.get("world_bible"):
        summary_parts.append(f"WORLD BIBLE: {global_ctx['world_bible']}")
    if global_ctx.get("style_guide"):
        summary_parts.append(f"STYLE GUIDE: {global_ctx['style_guide']}")

    if global_ctx.get("characters"):
        char_info = "CHARACTERS:\n" + "\n".join(
            [f"- {c['name']}: {c.get('description', '')}" for c in global_ctx["characters"]]
        )
        summary_parts.append(char_info)

    if global_ctx.get("sceneries"):
        scene_info = "SCENERIES:\n" + "\n".join(
            [f"- {s['name']}: {s.get('description', '')}" for s in global_ctx["sceneries"]]
        )
        summary_parts.append(scene_info)

    summary = "\n\n".join(summary_parts)
    full_script = ""

    if vectorstore:
        if not summary:
            world_info = km.query_world_rules("Describe el estilo artÃ­stico, personajes principales y escenarios.")
            summary = "\n".join([doc.page_content for doc in world_info])

        script_info = km.query_world_rules("Extrae el guiÃ³n completo o la trama detallada de la historia.")
        full_script = "\n".join([doc.page_content for doc in script_info])

    sm = StyleManager(state["project_id"])
    style_input = global_ctx.get("style_guide") or global_ctx.get("world_bible")
    current_style = sm.get_style_prompt()
    is_default = "Professional comic book" in current_style

    if style_input:
        print(f"DEBUG: [Agent B] Normalizing style using explicit guide. Input length: {len(style_input)}")
        sm.normalize_style(style_input)
    elif is_default and summary:
        print("DEBUG: [Agent B] Normalizing style using world summary excerpt.")
        sm.normalize_style(summary[:1000])
    else:
        print("DEBUG: [Agent B] Skipping style normalization (already set or no input available).")

    return {
        "current_step": "story_understanding",
        "world_model_summary": summary,
        "full_script": full_script,
        "reference_images": image_paths,
    }


@timed_function("node.story_understanding")
def story_understanding(state: AgentState):
    """Read the script in batches and extract page summaries and panel purposes."""
    print("--- STORY UNDERSTANDING (Deep Script Analysis) ---")

    full_script = state.get("full_script", "")
    sources = state.get("sources", [])
    project_id = state.get("project_id")

    raw_pages: Dict[int, str] = {}
    km = KnowledgeManager(project_id)

    pdf_loaded = False
    for url in sources:
        ext = os.path.splitext(url.split("?")[0])[1].lower()
        if ext == ".pdf":
            try:
                local_path = km.resolve_to_local_path(url)
                from langchain_community.document_loaders import PyPDFLoader

                with timed_step("story_understanding.load_pdf_pages"):
                    loader = PyPDFLoader(local_path)
                    pages = loader.load()
                for doc in pages:
                    pg = doc.metadata.get("page", 0) + 1
                    raw_pages[pg] = doc.page_content
                pdf_loaded = True
                print(f"DEBUG: [StoryUnderstanding] Loaded {len(raw_pages)} pages from PDF.")
                break
            except Exception as e:
                print(f"WARNING: [StoryUnderstanding] Could not load PDF pages: {e}")

    if not pdf_loaded and full_script:
        print("DEBUG: [StoryUnderstanding] No PDF pages loaded; splitting full_script into synthetic pages.")
        chars_per_page = 3000
        for i in range(0, len(full_script), chars_per_page):
            page_num = (i // chars_per_page) + 1
            raw_pages[page_num] = full_script[i : i + chars_per_page]

    if not raw_pages:
        print("WARNING: [StoryUnderstanding] No script content to analyze. Skipping.")
        return {
            "current_step": "world_model_builder",
            "page_summaries": {},
            "panel_purposes": {},
        }

    print(f"DEBUG: [StoryUnderstanding] Total pages to analyze: {len(raw_pages)}")

    batch_size = 10
    llm = ChatOpenAI(model=os.getenv("OPENAI_MODEL_ID"), temperature=0)
    page_summaries: Dict[int, str] = {}
    panel_purposes: Dict[str, str] = {}
    sorted_page_nums = sorted(raw_pages.keys())

    enable_parallel_story = os.getenv("ENABLE_PARALLEL_STORY", "1").strip().lower() not in {"0", "false", "no", "off"}
    max_story_workers = max(1, int(os.getenv("STORY_BATCH_CONCURRENCY", "2")))

    def process_story_batch(batch_page_nums: List[int]) -> Dict[str, object]:
        batch_llm = ChatOpenAI(model=os.getenv("OPENAI_MODEL_ID"), temperature=0)
        batch_text = ""
        for pg in batch_page_nums:
            batch_text += f"\n{raw_pages[pg]}"

        print(
            f"DEBUG: [StoryUnderstanding] Processing batch: pages "
            f"{batch_page_nums[0]}-{batch_page_nums[-1]} ({len(batch_text)} chars)"
        )

        prompt = f"""
        Actua como un Analista de Guiones de Comic experto.

        Tu tarea es leer el siguiente fragmento de guion y producir DOS tipos de analisis:

        1. RESUMEN DETALLADO POR PAGINA DE GUION
        Para cada pagina del guion de comic identificada en el fragmento, genera un resumen visual detallado que describa:
        - Que sucede narrativamente (accion, dialogo clave, progresion dramatica).
        - El tono emocional dominante (tension, calma, humor, misterio, etc.).
        - Los elementos visuales clave que un artista necesitaria saber.
        - Transiciones importantes respecto a la pagina anterior (si aplica).

        2. PROPOSITO SUBYACENTE DE CADA VINETA/PANEL
        Identifica cada vineta o panel descrito en el guion y asignale un proposito subyacente:
        - Cual es la intencion narrativa de esta vineta?
        - Que emocion debe evocar en el lector?
        - Que elemento visual es el foco principal?

        TEXTO DEL GUION:
        {batch_text}

        Responde UNICAMENTE en JSON con esta estructura:
        {{
            "page_summaries": {{
                "<numero_de_pagina>": "Resumen detallado de la pagina..."
            }},
            "panel_purposes": {{
                "page_<N>_panel_<M>": "Proposito subyacente: ..."
            }}
        }}

        REGLAS:
        - Para panel_purposes, usa la convencion "page_N_panel_M" donde N es el numero de pagina y M empieza en 1.
        - Si una pagina no tiene vinetas claramente definidas, trata toda la pagina como un solo panel.
        - Se preciso y detallado en los resumenes. Un buen resumen tiene 3-5 oraciones.
        - Los propositos deben ser concisos (1-2 oraciones) pero especificos.
        """

        try:
            with timed_step(f"story_understanding.batch_llm[{batch_page_nums[0]}-{batch_page_nums[-1]}]"):
                response = batch_llm.invoke(
                    [
                        SystemMessage(content="Eres un analista experto de guiones de cÃ³mic. Responde siempre en JSON vÃ¡lido."),
                        HumanMessage(content=prompt),
                    ]
                )

            content = response.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            batch_data = json.loads(content)
            return {
                "batch_page_nums": batch_page_nums,
                "page_summaries": batch_data.get("page_summaries", {}),
                "panel_purposes": batch_data.get("panel_purposes", {}),
            }
        except Exception as e:
            print(f"ERROR: [StoryUnderstanding] Batch {batch_page_nums[0]}-{batch_page_nums[-1]} failed: {e}")
            fallback_summaries = {}
            for pg in batch_page_nums:
                fallback_summaries[pg] = raw_pages[pg][:500] + "..." if len(raw_pages[pg]) > 500 else raw_pages[pg]
            return {
                "batch_page_nums": batch_page_nums,
                "page_summaries": fallback_summaries,
                "panel_purposes": {},
            }

    if enable_parallel_story and len(sorted_page_nums) > batch_size and max_story_workers > 1:
        print(
            f"DEBUG: [StoryUnderstanding] Parallel batch mode enabled with "
            f"{min(max_story_workers, len(sorted_page_nums))} workers."
        )

        story_batches = [
            sorted_page_nums[batch_start : batch_start + batch_size]
            for batch_start in range(0, len(sorted_page_nums), batch_size)
        ]
        batch_results: List[Dict[str, object]] = []

        with ThreadPoolExecutor(max_workers=min(max_story_workers, len(story_batches)), thread_name_prefix="story-batch") as executor:
            future_map = {
                submit_with_current_context(executor, process_story_batch, batch_page_nums): batch_page_nums
                for batch_page_nums in story_batches
            }
            for future in as_completed(future_map):
                batch_results.append(future.result())

        for batch_result in sorted(batch_results, key=lambda item: item["batch_page_nums"][0]):
            for pg_str, summary in batch_result.get("page_summaries", {}).items():
                try:
                    page_summaries[int(pg_str)] = summary
                except (ValueError, TypeError):
                    page_summaries[pg_str] = summary

            panel_purposes.update(batch_result.get("panel_purposes", {}))
            print(
                f"DEBUG: [StoryUnderstanding] Batch done. Summaries so far: {len(page_summaries)}, "
                f"Purposes so far: {len(panel_purposes)}"
            )
    else:
        for batch_start in range(0, len(sorted_page_nums), batch_size):
            batch_page_nums = sorted_page_nums[batch_start : batch_start + batch_size]
            batch_result = process_story_batch(batch_page_nums)
            for pg_str, summary in batch_result.get("page_summaries", {}).items():
                try:
                    page_summaries[int(pg_str)] = summary
                except (ValueError, TypeError):
                    page_summaries[pg_str] = summary
            panel_purposes.update(batch_result.get("panel_purposes", {}))
            print(
                f"DEBUG: [StoryUnderstanding] Batch done. Summaries so far: {len(page_summaries)}, "
                f"Purposes so far: {len(panel_purposes)}"
            )

    ordered_full_script = ""
    for pg in sorted(raw_pages.keys()):
        ordered_full_script += f"\n{raw_pages[pg]}"

    print(
        f"DEBUG: [StoryUnderstanding] Complete. {len(page_summaries)} page summaries, "
        f"{len(panel_purposes)} panel purposes extracted. full_script reordered ({len(ordered_full_script)} chars)."
    )

    return {
        "current_step": "world_model_builder",
        "page_summaries": page_summaries,
        "panel_purposes": panel_purposes,
        "full_script": ordered_full_script.strip(),
    }
