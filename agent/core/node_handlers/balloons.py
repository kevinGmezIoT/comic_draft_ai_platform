import json
import os

from langchain_openai import ChatOpenAI

from ..models import AgentState
from ..telemetry import timed_function, timed_step


@timed_function("node.balloon_generator")
def balloon_generator(state: AgentState):
    print("--- GENERATING DIALOGUE BALLOONS ---")
    llm = ChatOpenAI(model=os.getenv("OPENAI_MODEL_ID"), temperature=0)

    panels_context = []
    for p in state["panels"]:
        panels_context.append(
            {
                "id": p.get("id"),
                "scene_description": p.get("scene_description", ""),
                "characters": p.get("characters", []),
            }
        )

    prompt = f"""
    BasÃ¡ndote en el GUION y la descripciÃ³n de los PANELES, genera los diÃ¡logos y cajas de narraciÃ³n.
    
    GUION:
    {state['full_script']}
    
    PANELES:
    {json.dumps(panels_context, indent=2)}
    
    Para cada panel, devuelve una lista de globos con:
    - type: "dialogue" | "narration"
    - character: nombre del personaje (o null si es narraciÃ³n)
    - text: el contenido del texto
    - position_hint: "top-left" | "top-right" | "bottom-center" (donde crees que queda mejor)
    
    Responde en JSON:
    {{"panels": [{{"id": "...", "balloons": [...]}}]}}
    """

    try:
        with timed_step("balloon_generator.llm_invoke"):
            response = llm.invoke(prompt)
        content = response.content.strip()
        if content.startswith("```json"):
            content = content[7:-3].strip()
        data = json.loads(content)

        balloons_map = {str(p["id"]): p["balloons"] for p in data.get("panels", [])}

        updated_panels = []
        for p in state["panels"]:
            p_id = str(p["id"])
            p["balloons"] = balloons_map.get(p_id, [])
            print(f"DEBUG: Panel {p_id} got {len(p['balloons'])} balloons.")
            updated_panels.append(p)

        return {"panels": updated_panels, "current_step": "merger"}
    except Exception as e:
        print(f"Error generating balloons: {e}")
        return {"current_step": "error"}
