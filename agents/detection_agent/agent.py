from pathlib import Path
from google.adk.agents import Agent
from tools.bigquery.partition_detection import detect_missing_partition_filter
from config.settings import MODEL_NAME

INSTRUCTIONS_PATH = (Path(__file__).parent / "instructions.md")


DETECTION_AGENT_INSTRUCTION = (INSTRUCTIONS_PATH.read_text(encoding="utf-8"))


detection_agent = Agent(
    name="detection_agent",
    model=MODEL_NAME,
    description=(
        "Detects missing partition filters "
        "in BigQuery queries."
    ),
    instruction=DETECTION_AGENT_INSTRUCTION
)