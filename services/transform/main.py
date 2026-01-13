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


def extract(pattern, text, group=1):
    match = re.search(
        pattern, text, re.IGNORECASE | re.MULTILINE
    )
    return match.group(group).strip() if match else None


def fetch_raw_ocr_rows(limit=1):
    query = f"""
    SELECT
      correlation_id,
      file_name,
      text
    FROM `{PROJECT_ID}.{DATASET}.{SOURCE_TABLE}`
    WHERE text IS NOT NULL
    AND PROCESSED_BY IS NULL
    LIMIT {limit}
    """
    return client.query(query).result()

def normalize_amount(value: str) -> float:
    return float(
        value.replace(" ", "").replace(",", ".")
    )


def run_transformer():
    rows = list(fetch_raw_ocr_rows())
    # logger.info(f"Fetched {len(rows)} rows")
    

    for row in rows:
        print(repr(row.text))

        data = {}

        data["invoice_number"] = extract(
            r"Invoice\s*no[:\s]+(\d+)", row.text
        )

        data["date_of_issue"] = extract(
            r"Date of issue[:\s]*\n?([0-9/.-]+)", row.text
        )

        seller_block = extract(
            r"Seller:\n(.*?)(?=\nClient:)",
            row.text,
            group=1
        )
        logger.info(f'seller_block: {seller_block}')

        if seller_block:
            lines = [
                l.strip() for l in seller_block.splitlines() if l.strip()
            ]
            data["seller_name"] = lines[0]
            data["seller_address"] = " ".join(lines[1:-1])
            data["seller_tax_id"] = extract(
                r"Tax Id[:\s]+([\d-]+)", seller_block
            )
        
        client_block = extract(
            r"Client:\s*(.*?)\n\s*ITEMS",
            row.text,
            group=1
        )

        if client_block:
            lines = [
                l.strip() for l in client_block.splitlines() if l.strip()
            ]
            data["client_name"] = lines[0]
            data["client_address"] = " ".join(lines[1:-1])
            data["client_tax_id"] = extract(
                r"Tax Id[:\s]+([\d-]+)", client_block
            )

        totals = re.findall(r"\$\s*([\d\s.,]+)", row.text)

        if len(totals) >= 3:
            data["total_net"] = normalize_amount(totals[-3])
            data["total_vat"] = normalize_amount(totals[-2])
            data["total_gross"] = normalize_amount(totals[-1])

        logger.info(f"Extracted Data: {data}")

if __name__ == "__main__":
    run_transformer()
    # text = """Seller:
    # Nicholson, Miller and Webster
    # USS Lee
    # FPO AE 74393
    # Tax Id: 962-88-9077
    # IBAN: GB23TMKM50357047352524
    # Client:"""

    # match = re.search(
    #     r"Seller:\s*(.*?)\s*Client:",
    #     text,
    #     re.DOTALL
    # )

    # print(match.group(1))