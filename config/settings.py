import os

from dotenv import load_dotenv


load_dotenv()


PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT","bq-verse-sandbox-052025")

METRICS_API_BASE_URL = os.getenv("METRICS_API_BASE_URL", "http://20.15.164.79:8080").rstrip("/")

BQ_LOCATION = os.getenv("BQ_LOCATION","US")

MODEL_NAME = os.getenv("MODEL_NAME","gemini-3.6-flash")

LOG_LEVEL = os.getenv("LOG_LEVEL","INFO")

BQ_RESULTS_DATASET = os.getenv("BQ_RESULTS_DATASET","bq_support_agent")

BQ_RESULTS_TABLE = os.getenv("BQ_RESULTS_TABLE","incident_results")

BQ_RAW_RESULTS_TABLE = os.getenv("BQ_RAW_RESULTS_TABLE","incident_raw_responses")
