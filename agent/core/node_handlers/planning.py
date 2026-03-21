import json
import os

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from ..knowledge import CanonicalStore, CharacterManager, SceneryManager
from ..models import AgentState
from ..telemetry import timed_function


@timed_function("node.planner")
def planner(state: AgentState):
    existing_panels = state.get("panels", [])
    max_panels = state.get("max_panels")

    target_page = state.get("page_number")
    preserved_panels = []

    if target_page:
        preserved_panels = [p for p in existing_panels if p.get("page_number") != target_page]
        print(f"DEBUG: [SCOPED PLANNING] Preserving {len(preserved_panels)} panels from other pages. Target Page: {target_page}")

    page_structure = {}
    if existing_panels:
        for p in existing_panels:
            p_num = p.get("page_number", 1)
            page_structure[p_num] = page_structure.get(p_num, 0) + 1

    structure_str = ""
    if page_structure:
        parts = [f"PÃ¡gina {k}: {v} paneles" for k, v in sorted(page_structure.items())]
        structure_str = f"ESTRUCTURA DE LIENZO ACTUAL (REQUERIDA): {', '.join(parts)}."

    print("--- STRATEGIC PLANNING (Batched) ---")
    canon = CanonicalStore(state["project_id"])
    cm = CharacterManager(state["project_id"], canon=canon)
    scm = SceneryManager(state["project_id"], canon=canon)

    existing_chars = list(cm.canon.data.get("characters", {}).keys())
    full_existing_scenes = scm.canon.data.get("sceneries", {})
    existing_scenes = list(full_existing_scenes.keys())

    assets_context = ""
    if existing_chars or existing_scenes:
        assets_context = "LISTA DE ACTIVOS EXISTENTES (USA ESTOS NOMBRES EXACTOS):\n"
        if existing_chars:
            assets_context += f"- PERSONAJES: {', '.join(existing_chars)}\n"
        if existing_scenes:
            assets_context += "- ESCENARIOS:\n"
            for scene in existing_scenes:
                assets_context += f"  - {scene}: {full_existing_scenes[scene].get('description', '')}\n"
        assets_context += (
            "Si el guiÃ³n requiere un escenario o personaje que no estÃ¡ en esta lista, "
            "intenta usar el mÃ¡s parecido, pero si se diferencia mucho, no inventes nuevos escenarios ni personajes."
        )

    llm = ChatOpenAI(model=os.getenv("OPENAI_MODEL_ID"), temperature=0.2)

    if not state.get("full_script") or len(state["full_script"].strip()) < 5:
        raise ValueError("DEBUG ERROR: El script estÃ¡ vacÃ­o o es demasiado corto para planificar.")

    page_summaries = state.get("page_summaries", {})
    full_script = state.get("full_script", "")

    script_pages = {}
    chars_per_page = 3000
    for i in range(0, len(full_script), chars_per_page):
        page_num = (i // chars_per_page) + 1
        script_pages[page_num] = full_script[i : i + chars_per_page]
    print(f"DEBUG: [PLANNER] Split full_script into {len(script_pages)} page chunks for planning.")

    max_pages_comic = state.get("max_pages", 3)
    max_panels_comic = state.get("max_panels", 0)
    sorted_script_pages = sorted(script_pages.keys())

    panels_per_page = max(1, max_panels_comic // max_pages_comic) if max_panels_comic and max_pages_comic else 3
    batch_size = 10
    use_batching = len(sorted_script_pages) > batch_size

    if use_batching:
        print(f"DEBUG: [PLANNER] Large script detected ({len(sorted_script_pages)} pages). Using batched planning.")
    else:
        print(f"DEBUG: [PLANNER] Script fits in single call ({len(sorted_script_pages)} pages).")

    def get_narrative_context_for_pages(page_nums: list) -> str:
        if not page_summaries:
            return ""
        context_parts = []
        for pg in page_nums:
            summary = page_summaries.get(pg, page_summaries.get(str(pg), ""))
            if summary:
                context_parts.append(f"PÃ¡g {pg}: {summary}")
        if context_parts:
            return "CONTEXTO NARRATIVO (resumen de las pÃ¡ginas del guiÃ³n):\n" + "\n".join(context_parts)
        return ""

    def plan_batch(
        batch_script_text: str,
        narrative_context: str,
        comic_page_start: int,
        comic_page_end: int,
        panels_for_batch: int,
        previous_panel_context: str,
    ) -> list:
        batch_prompt = f"""
        BasÃ¡ndote en el siguiente SUMMARY del mundo y SCRIPT:
        
        {assets_context}
        
        SUMMARY:
        {state['world_model_summary'][:1500]}
        
        {narrative_context}
        
        SCRIPT (GuiÃ³n completo con descripciÃ³n detallada de cada viÃ±eta):
        {batch_script_text}
        
        TAMAÃ‘O DE PÃGINA RECOMENDADO: {state.get('canvas_dimensions', '800x1100 (A4)')}
        ESTILO DE LAYOUT: {state.get('layout_style', 'dynamic')}
        {structure_str}

        {'ESTÃS REGENERANDO ÃšNICAMENTE LA PÃGINA ' + str(target_page) if target_page else f'ESTÃS GENERANDO LAS PÃGINAS {comic_page_start} A {comic_page_end} DEL CÃ“MIC'}
        
        {f'CONTEXTO DEL PANEL ANTERIOR (para mantener continuidad): {previous_panel_context}' if previous_panel_context else ''}
        
        ORDEN DE PRIORIDAD:
        - **DISTRIBUCIÃ“N**: Genera aproximadamente {panels_for_batch} paneles repartidos entre las pÃ¡ginas {comic_page_start} a {comic_page_end}.
        - **ÃNDICE DE ORDEN (CRÃTICO)**: El campo `order_in_page` DEBE EMPEZAR EN 0 para el primer panel de cada pÃ¡gina. (Ej: 0, 1, 2...). No empieces en 1.
        - Los `page_number` DEBEN ir de {comic_page_start} a {comic_page_end}.
        - **CONTINUIDAD**: El primer panel debe ser la continuaciÃ³n inmediata del contexto anterior (si existe).
        
        FORMATO JSON OBLIGATORIO:
        {{
            "panels": [
                {{
                    "page_number": {comic_page_start},
                    "order_in_page": 0,
                    "scene_description": "DescripciÃ³n detallada de la escena...",
                    "script": "parte del guiÃ³n que describe detalladamente el panel o viÃ±eta, no solo el diÃ¡logo sino la descripciÃ³n completa de la escena.",
                    "characters": ["Nombre del Personaje"],
                    "scenery": "Lugar donde se desarrolla este panel o viÃ±eta",
                    "style": "Estilo de dibujo"
                }}
            ]
        }}
        
        Responde ÃšNICAMENTE con un JSON vÃ¡lido. No incluyas texto fuera del bloque de cÃ³digo JSON.
        """

        response = llm.invoke(
            [
                SystemMessage(content="Eres un director de arte de cÃ³mics experto en descomposiciÃ³n de guiones. Responde SIEMPRE con un JSON vÃ¡lido."),
                HumanMessage(content=batch_prompt),
            ]
        )

        content = response.content.strip()
        print(f"DEBUG: [PLANNER BATCH] Pages {comic_page_start}-{comic_page_end} Output: {content[:200]}...")

        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()

        return json.loads(content)

    all_panels = []

    try:
        if not use_batching:
            batch_text = ""
            for pg in sorted_script_pages:
                batch_text += f"\n{script_pages[pg]}"

            comic_page_start = target_page if target_page else 1
            comic_page_end = target_page if target_page else max_pages_comic
            narrative_ctx = get_narrative_context_for_pages(sorted_script_pages)

            data = plan_batch(
                batch_text,
                narrative_ctx,
                comic_page_start,
                comic_page_end,
                max_panels_comic if max_panels_comic else panels_per_page * max_pages_comic,
                "",
            )
            all_panels = _extract_panels_from_data(data)
        else:
            previous_context = ""
            script_to_comic_ratio = max_pages_comic / len(sorted_script_pages) if sorted_script_pages else 1

            for batch_idx in range(0, len(sorted_script_pages), batch_size):
                batch_page_nums = sorted_script_pages[batch_idx : batch_idx + batch_size]
                batch_text = ""
                for pg in batch_page_nums:
                    batch_text += f"\n{script_pages[pg]}"

                comic_page_start = int(batch_idx * script_to_comic_ratio) + 1
                comic_page_end = min(int((batch_idx + len(batch_page_nums)) * script_to_comic_ratio) + 1, max_pages_comic)
                if comic_page_end < comic_page_start:
                    comic_page_end = comic_page_start

                batch_panels_count = panels_per_page * (comic_page_end - comic_page_start + 1)

                print(
                    f"DEBUG: [PLANNER BATCH] Script pages {batch_page_nums[0]}-{batch_page_nums[-1]} -> "
                    f"Comic pages {comic_page_start}-{comic_page_end} ({batch_panels_count} panels)"
                )

                narrative_ctx = get_narrative_context_for_pages(batch_page_nums)
                data = plan_batch(batch_text, narrative_ctx, comic_page_start, comic_page_end, batch_panels_count, previous_context)
                batch_panels = _extract_panels_from_data(data)

                if batch_panels:
                    last = batch_panels[-1]
                    previous_context = (
                        f"PÃ¡gina {last.get('page_number')}, Escena: {last.get('scene_description', '')[:200]}, "
                        f"Personajes: {', '.join(last.get('characters', []))}"
                    )
                    all_panels.extend(batch_panels)
                    print(f"DEBUG: [PLANNER BATCH] Got {len(batch_panels)} panels. Total so far: {len(all_panels)}")

        if not all_panels:
            raise ValueError("No panels were generated by the LLM from the script.")

        page_counts = {}
        existing_layout_map = {
            (p.get("page_number"), p.get("order_in_page")): p.get("layout")
            for p in existing_panels
            if p.get("layout") and p.get("layout").get("w", 0) > 0
        }

        for i, p in enumerate(all_panels):
            p_id = str(p.get("id")) if p.get("id") else f"p_{i}"
            p["id"] = p_id
            p.setdefault("image_url", "")
            p.setdefault("status", "pending")
            p.setdefault("characters", [])

            p_num = target_page if target_page else p.get("page_number", 1)
            p["page_number"] = p_num
            p_order = page_counts.get(p_num, 0)
            p["order_in_page"] = p_order
            page_counts[p_num] = p_order + 1

            prev_layout = existing_layout_map.get((p_num, p_order))
            if prev_layout:
                print(f"DEBUG: [PLANNER] Inheriting Layout for PÃ¡g {p_num}, Orden {p_order} -> {prev_layout}")
                p["layout"] = prev_layout
            else:
                p.setdefault("layout", {})

            if not p.get("prompt"):
                p["prompt"] = "Cinematic comic panel"

        final_panels = preserved_panels + all_panels
        return {"panels": final_panels, "current_step": "layout_designer"}
    except Exception as e:
        print(f"CRITICAL ERROR en planner: {e}")
        import traceback

        traceback.print_exc()
        raise e


def _extract_panels_from_data(data) -> list:
    """Extract panel-like dictionaries from flexible LLM JSON responses."""

    def find_all_panels(obj):
        found = []
        keys_to_match = [
            "scene_description",
            "prompt",
            "descripcion",
            "guion",
            "escena",
            "accion",
            "texto",
            "description",
            "panel_description",
        ]
        if isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict) and any(k in item for k in keys_to_match):
                    found.append(item)
                else:
                    found.extend(find_all_panels(item))
        elif isinstance(obj, dict):
            if any(k in obj for k in keys_to_match):
                found.append(obj)
            else:
                for value in obj.values():
                    found.extend(find_all_panels(value))
        return found

    panels = find_all_panels(data)
    if not panels and isinstance(data, list):
        panels = data
    return panels
