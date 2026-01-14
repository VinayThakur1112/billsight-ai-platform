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
SOURCE_TABLE = os.getenv("BILL_SIGHT_RAW_TABLE")
SUMMARY_TABLE = os.getenv("BILL_SIGHT_SUMMARY_TABLE")
ITEMS_TABLE = os.getenv("BILL_SIGHT_ITEMS_TABLE")


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

def bigquery_insert(data: str, table_id: str):
    client = bigquery.Client()
    
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ArrayQueryParameter(
                "rows",
                "STRUCT<correlation_id STRING, invoice_number STRING, " \
                "date_of_issue STRING, seller_name, STRING>, " \
                "seller_address STRING, seller_tax_id STRING, " \
                "client_name STRING, client_address STRING, " \
                "client_tax_id STRING, total_net STRING, " \
                "total_vat STRING, total_gross STRING",
                data
            )
        ]
    )

    query = f"""
    MERGE `{table_id}` T
    USING (
    SELECT * FROM UNNEST(@rows)
    ) S
    ON T.correlation_id = S.correlation_id
    WHEN NOT MATCHED THEN
    INSERT (correlation_id, invoice_number, date_of_issue, seller_name,
    seller_address, seller_tax_id, client_name, client_address, client_tax_id
    total_net, total_vat, total_gross)
    VALUES (S.correlation_id, S.invoice_number, S.date_of_issue, S.seller_name,
    S.seller_address, S.seller_tax_id, S.client_name, S.client_address, 
    S.client_tax_id, S.total_net, S.total_vat, S.total_gross)
    """

    client.query(query, job_config=job_config).result()



def run_transformer():
    rows = list(fetch_raw_ocr_rows())
    # logger.info(f"Fetched {len(rows)} rows")

    rows_to_insert = []
    for row in rows:
        print(repr(row))

        data = {}

        data["invoice_number"] = extract(
            r"Invoice\s*no[:\s]+(\d+)", row.text
        )

        data["date_of_issue"] = extract(
            r"Date of issue[:\s]*\n?([0-9/.-]+)", row.text
        )

        seller_block = extract(
            r"Seller:(.*?)(?=Client:)",
            repr(row.text),
            group=1
        )
        seller_block = seller_block.replace("\\n", " ").replace("\n", " ")
        # logger.info(f'seller_block: {seller_block}')

        if seller_block:
            
            data["seller_name"] = extract(
                r"(.*?)(?=Tax Id:)",
                seller_block,
                group=1
            )
            data["seller_address"] = extract(
                r"(.*?)(?=Tax Id:)",
                seller_block,
                group=1
            )
            data["seller_tax_id"] = extract(
                r"Tax Id:(.*?)(?=IBAN:)",
                seller_block,
                group=1
            )
        
        client_block = extract(
            r"Client:(.*?)(?=ITEMS)",
            repr(row.text),
            group=1
        )
        client_block = client_block.replace("\\n", " ").replace("\n", " ")
        logger.info(f'client_block: {client_block}')

        if client_block:
            
            data["client_name"] = extract(
                r"(.*?)(?=Tax Id:)",
                client_block,
            )
            data["client_address"] = extract(
                r"(.*?)(?=Tax Id:)",
                client_block,
            )
            data["client_tax_id"] = extract(
                r"Tax Id:(.*)", 
                client_block
            )

        totals = re.findall(r"\$\s*([\d\s.,]+)", row.text)

        if len(totals) >= 3:
            data["total_net"] = normalize_amount(totals[-3])
            data["total_vat"] = normalize_amount(totals[-2])
            data["total_gross"] = normalize_amount(totals[-1])

        logger.info(f"Extracted Data: {data}")

        table_row = {
            "correlation_id": row.correlation_id,
            "file_name": row.file_name,
            "invoice_number": data["invoice_number"],
            "date_of_issue": data["date_of_issue"],
            "seller_name": data["seller_name"],
            "seller_address": data["seller_address"],
            "seller_tax_id": data["seller_tax_id"],
            "client_name": data["client_name"],
            "client_address": data["client_address"],
            "client_tax_id": data["client_tax_id"],
            "total_net": data["total_net"],
            "total_vat": data["total_vat"],
            "total_gross": data["total_gross"],
        }

        rows_to_insert.append(table_row)

    # insert into table
    bigquery_insert(rows_to_insert, f"{PROJECT_ID}.{DATASET}.{SUMMARY_TABLE}")

if __name__ == "__main__":
    run_transformer()