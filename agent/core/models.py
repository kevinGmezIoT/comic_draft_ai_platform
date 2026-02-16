from typing import TypedDict, List, Dict, Annotated

class Panel(TypedDict):
    id: str
    page_number: int
    order_in_page: int
    prompt: str
    scene_description: str
    characters: List[str]
    image_url: str
    status: str
    layout: dict
    balloons: List[dict]
    instructions: str
    panel_style: str
    current_image_url: str
    reference_image_url: str
    scenery: str
    script: str

class AgentState(TypedDict):
    project_id: str
    sources: List[str]
    max_pages: int
    max_panels: int
    layout_style: str  # "dynamic" | "vertical" | "grid"
    world_model_summary: str
    style_guide: str
    full_script: str
    script_outline: List[str]
    panels: List[Panel]
    merged_pages: List[dict]  # [{page_number: 1, image_url: "..."}]
    canvas_dimensions: str
    plan_only: bool
    current_step: str
    action: str  # "generate" | "regenerate_panel" | "regenerate_merge"
    panel_id: str
    page_number: int  # For selective page merge
    instructions: str  # User instructions for regeneration
    current_image_url: str  # Context for I2I
    reference_image_url: str  # Visual reference context
    continuity_state: Dict[str, Dict]  # State tracking for Agent H
    reference_images: List[str]
    global_context: Dict  # Optional metadata from backend
    page_summaries: Dict[int, str]  # Per-page detailed summaries from story understanding
    panel_purposes: Dict[str, str]  # Panel key -> underlying purpose/intent
