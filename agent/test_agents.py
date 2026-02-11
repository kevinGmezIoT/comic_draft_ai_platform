import os
import json
from dotenv import load_dotenv
from core.knowledge import CharacterManager, StyleManager, CanonicalStore
from core.graph import PromptBuilder, ContinuitySupervisor, Panel

load_dotenv(override=True)

def test_modular_agents():
    project_id = "test_project_123"
    print(f"--- Testing Project: {project_id} ---")
    
    # 1. Initialize Managers
    cm = CharacterManager(project_id)
    sm = StyleManager(project_id)
    pb = PromptBuilder(project_id)
    cs = ContinuitySupervisor(project_id)
    
    # 2. Register Character (Simulator)
    print("\n[Step 1] Registering Character 'Ana'...")
    # Mocking description and refs as if they came from ProjectWizard
    ana_desc = "Una joven guerrera cyber-noir con una chaqueta de cuero negra."
    # For extraction test, we'd need a real URL. Here we'll manually add traits if extraction fails or skip.
    cm.register_character("Ana", ana_desc, []) # No URL for automated test to avoid external dependencies
    
    # Manually injecting some traits as if Agent B extraction worked
    cm.canon.update_character("Ana", {"visual_traits": ["cabello azul neon", "brazo mecanico plateado", "ojos amarillos"]})
    
    # 3. Normalize Style (Simulator)
    print("\n[Step 2] Normalizing Style Guide...")
    style_guide = "Estilo expresionista, lineas gruesas, atmosfera de lluvia constante y luces de neon."
    # sm.normalize_style(style_guide) # Requires LLM call
    sm.canon.update_style({"style_tokens": ["thick noir lines", "neon lighting", "rainy atmosphere", "expressionist"]})
    
    # 4. Test Continuity State (Agent H)
    print("\n[Step 3] Testing Continuity Supervisor...")
    initial_state = {"Ana": {"herida": "ninguna", "objeto": "katana"}}
    panel_action = Panel(
        id="p1", 
        scene_description="Ana es herida en el brazo derecho durante un combate intenso.",
        characters=["Ana"]
    )
    
    # new_state = cs.update_state(initial_state, panel_action) # Requires LLM call
    # Simulating update
    new_state = {"Ana": {"herida": "corte sangrante en brazo derecho", "objeto": "katana"}}
    print(f"Old State: {initial_state}")
    print(f"New State (Simulated): {new_state}")
    
    # 5. Build Layered Prompt (Agent F)
    print("\n[Step 4] Building Layered Prompt...")
    panel_p2 = Panel(
        id="p2",
        scene_description="Ana se levanta con esfuerzo mientras la lluvia cae sobre ella.",
        characters=["Ana"],
        layout={"w": 100, "h": 50}
    )
    
    final_prompt = pb.build_panel_prompt(panel_p2, "Cyber-Noir Neo Tokyo", new_state)
    print(f"FINAL PROMPT:\n---\n{final_prompt}\n---")
    
    # Assertions for the developer to see
    assert "neon lighting" in final_prompt
    assert "brazo mecanico plateado" in final_prompt
    assert "corte sangrante en brazo derecho" in final_prompt
    print("\n[SUCCESS] Prompt Builder integrated Canonical Traits and Continuity State correctly.")

if __name__ == "__main__":
    test_modular_agents()
