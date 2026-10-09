from pathlib import Path
from google.adk.agents import Agent
from config.settings import MODEL_NAME

INSTRUCTIONS_PATH = Path(__file__).parent / "instructions.md"
REMEDIATION_AGENT_INSTRUCTIONS = INSTRUCTIONS_PATH.read_text(encoding="utf-8")

remediation_agent = Agent(
    name="remediation_agent",
    model=MODEL_NAME,
    description=(
        "Determines and recommends remediation for issues "
        "detected and diagnosed by the support workflow."
    ),
    instruction=REMEDIATION_AGENT_INSTRUCTIONS
)