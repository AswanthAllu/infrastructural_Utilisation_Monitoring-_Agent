from pathlib import Path
import os
from dotenv import load_dotenv

# Ensure .env is loaded reliably from the backend directory
BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
load_dotenv(BACKEND_DIR / "tests" / ".env")
load_dotenv()

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "bq-verse-sandbox-052025")
METRICS_API_BASE_URL = os.getenv("METRICS_API_BASE_URL", "http://20.15.164.79:8080").rstrip("/")
BQ_LOCATION = os.getenv("BQ_LOCATION", "US")

# Centralized LLM & Model Configuration for all Agents (CPU, Disk, Memory)
LLM_ENDPOINT = os.getenv(
    "LLM_ENDPOINT",
    os.getenv(
        "AZURE_OPENAI_ENDPOINT",
        "https://infrastructuremonitoringagent.openai.azure.com/openai/responses?api-version=2025-04-01-preview"
    )
)
AZURE_OPENAI_ENDPOINT = LLM_ENDPOINT

LLM_API_KEY = os.getenv(
    "LLM_API_KEY",
    os.getenv("AZURE_OPENAI_API_KEY", os.getenv("OPENAI_API_KEY", ""))
)
AZURE_OPENAI_API_KEY = LLM_API_KEY

MODEL_NAME = os.getenv("MODEL_NAME", "5.6 luna")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
BQ_RESULTS_DATASET = os.getenv("BQ_RESULTS_DATASET", "bq_support_agent")
BQ_RESULTS_TABLE = os.getenv("BQ_RESULTS_TABLE", "incident_results")
BQ_RAW_RESULTS_TABLE = os.getenv("BQ_RAW_RESULTS_TABLE", "incident_raw_responses")

