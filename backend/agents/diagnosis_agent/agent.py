from pathlib import Path
from google.adk.agents import Agent
from config.settings import MODEL_NAME

INSTRUCTIONS_PATH = Path(__file__).parent / "instructions.md"
DIAGNOSIS_AGENT_INSTRUCTION = INSTRUCTIONS_PATH.read_text(encoding="utf-8")

diagnosis_agent = Agent(
    name="diagnosis_agent",
    model=MODEL_NAME,
    description="Identifies diagnosis for the issue detected by the detection_agent",
    instruction=DIAGNOSIS_AGENT_INSTRUCTION,
)