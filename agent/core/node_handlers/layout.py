from ..models import AgentState
from ..telemetry import timed_function


@timed_function("node.layout_designer")
def layout_designer(state: AgentState):
    print("--- DEFINING PAGE LAYOUTS (Templates) ---")
    panels = state.get("panels", [])
    if not panels:
        print("--- WARNING: No panels to design layout for. ---")
        return {"current_step": "generator"}

    panels_needing_layout = []
    for p in panels:
        ly = p.get("layout", {})
        px_w = ly.get("w", 0)
        if not (ly and px_w and float(px_w) > 0):
            panels_needing_layout.append(p)

    print(f"DEBUG: Total panels: {len(panels)}, Panels needing layout: {len(panels_needing_layout)}")

    if not panels_needing_layout:
        print("--- SKIPPING LAYOUT DESIGN (All panels have layout defined) ---")
        return {"panels": panels, "current_step": "generator"}

    pages = {}
    for p in panels:
        p_num = p["page_number"]
        if p_num not in pages:
            pages[p_num] = []
        pages[p_num].append(p)

    updated_panels = []
    layout_pref = state.get("layout_style", "dynamic")

    for page_num, p_list in pages.items():
        count = len(p_list)
        p_list = sorted(p_list, key=lambda x: x["order_in_page"])

        for i, p in enumerate(p_list):
            ly = p.get("layout", {})
            w_val = ly.get("w") or ly.get("width")
            try:
                if w_val and float(w_val) > 0:
                    print(
                        f"DEBUG: [LAYOUT DESIGNER] Preservando Layout Panel {p.get('id')} -> "
                        f"x:{ly.get('x')}, y:{ly.get('y')}, w:{w_val}, h:{ly.get('h')}"
                    )
                    updated_panels.append(p)
                    continue
            except (ValueError, TypeError):
                pass

            print(f"DEBUG: [LAYOUT DESIGNER] DiseÃ±ando Layout para Panel {p.get('id')} (PÃ¡g {page_num}, Index {i})")

            if layout_pref == "vertical":
                h_per_panel = 100 / count
                p["layout"] = {"x": 0, "y": i * h_per_panel, "w": 100, "h": h_per_panel}
            elif layout_pref == "grid" and count >= 4:
                row = i // 2
                col = i % 2
                p["layout"] = {"x": col * 50, "y": row * 50, "w": 50, "h": 50}
            else:
                if count == 1:
                    p["layout"] = {"x": 0, "y": 0, "w": 100, "h": 100}
                elif count == 2:
                    prompt_lower = str(p.get("prompt", "")).lower()
                    if "enfrentados" in prompt_lower or "confrontation" in prompt_lower or "face-off" in prompt_lower:
                        if i == 0:
                            p["layout"] = {"x": 5, "y": 10, "w": 42, "h": 80}
                        else:
                            p["layout"] = {"x": 53, "y": 10, "w": 42, "h": 80}
                    elif "vertical split" in prompt_lower:
                        p["layout"] = {"x": i * 50, "y": 0, "w": 50, "h": 100}
                    else:
                        p["layout"] = {"x": 0, "y": i * 50, "w": 100, "h": 50}
                elif count == 3:
                    if i == 0:
                        p["layout"] = {"x": 0, "y": 0, "w": 100, "h": 40}
                    else:
                        p["layout"] = {"x": (i - 1) * 50, "y": 40, "w": 50, "h": 60}
                elif count == 4:
                    p["layout"] = {"x": (i % 2) * 50, "y": (i // 2) * 50, "w": 50, "h": 50}
                else:
                    row = i // 2
                    col = i % 2
                    h = 100 / ((count + 1) // 2)
                    p["layout"] = {"x": col * 50, "y": row * h, "w": 50, "h": h}

            updated_panels.append(p)

    accounted_ids = set(str(p.get("id")) for p in updated_panels)
    for p in panels:
        if str(p.get("id")) not in accounted_ids:
            updated_panels.append(p)

    return {"panels": updated_panels, "current_step": "generator"}
