import re
from datetime import datetime
import os
from services.common.logging import get_logger

from google.cloud import bigquery
client = bigquery.Client()

logger = get_logger(__name__)

from dotenv import load_dotenv
load_dotenv()

PROJECT_ID = os.getenv("PROJECT_ID")
DATASET = os.getenv("BQ_DATASET")
SOURCE_TABLE = os.getenv("BQ_RAW_OCR_TABLE")

def fetch_raw_ocr_rows(limit=1):
    query = f"""
    SELECT
      correlation_id,
      text
    FROM `{PROJECT_ID}.{DATASET}.{SOURCE_TABLE}`
    WHERE text IS NOT NULL
    AND PROCESSED_BY IS NULL
    LIMIT {limit}
    """
    return client.query(query).result()

def run_transformer():
    rows = list(fetch_raw_ocr_rows())
    logger.info(f"Fetched {len(rows)} rows")

    for row in rows:
        print(row)

if __name__ == "__main__":
    run_transformer()