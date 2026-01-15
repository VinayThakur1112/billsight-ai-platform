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

def bigquery_insert(data, table_id: str):
    client = bigquery.Client()
    # logger.info(data)

    struct_data = []
    for row in data:
        struct_data.append(
            bigquery.StructQueryParameter(
                "row_placeholder", 
                bigquery.ScalarQueryParameter(
                    "correlation_id", "STRING", row["correlation_id"]),
                bigquery.ScalarQueryParameter(
                    "file_name", "STRING", row["file_name"]),
                bigquery.ScalarQueryParameter(
                    "invoice_number", "STRING", row["invoice_number"]),
                bigquery.ScalarQueryParameter(
                    "Date_of_issue", "STRING", row["Date_of_issue"]),
                bigquery.ScalarQueryParameter(
                    "seller_name", "STRING", row["seller_name"]),
                bigquery.ScalarQueryParameter(
                    "seller_address", "STRING", row["seller_address"]),
                bigquery.ScalarQueryParameter(
                    "seller_tax_id", "STRING", row["seller_tax_id"]),
                bigquery.ScalarQueryParameter(
                    "client_name", "STRING", row["client_name"]),
                bigquery.ScalarQueryParameter(
                    "client_address", "STRING", row["client_address"]),
                bigquery.ScalarQueryParameter(
                    "client_tax_id", "STRING", row["client_tax_id"]),
                bigquery.ScalarQueryParameter(
                    "total_net", "STRING", row["total_net"]),
                bigquery.ScalarQueryParameter(
                    "total_vat", "STRING", row["total_vat"]),
                bigquery.ScalarQueryParameter(
                    "total_gross", "STRING", row["total_gross"])
            )
        )
    
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ArrayQueryParameter("rows", "RECORD", struct_data)
        ]
    )

    query = f"""
        MERGE `{table_id}` T
        USING (
        SELECT correlation_id, file_name, invoice_number, Date_of_issue,
        seller_name, seller_address, seller_tax_id, client_name,
        client_address, client_tax_id, total_net, total_vat, 
        total_gross FROM UNNEST(@rows)
        ) S
        ON T.correlation_id = S.correlation_id
        WHEN NOT MATCHED THEN
        INSERT (
            correlation_id, 
            file_name,
            invoice_number,
            Date_of_issue,
            seller_name,
            seller_address,
            seller_tax_id,
            client_name,
            client_address,
            client_tax_id,
            total_net,
            total_vat,
            total_gross
        )
        VALUES (
            S.correlation_id, 
            S.file_name,
            S.invoice_number,
            S.Date_of_issue,
            S.seller_name,
            S.seller_address,
            S.seller_tax_id,
            S.client_name,
            S.client_address,
            S.client_tax_id,
            S.total_net,
            S.total_vat,
            S.total_gross
        )
    """

    response_val = client.query(query, job_config=job_config).result()
    logger.info(f"insertion response: {response_val}")



def run_transformer():
    rows = list(fetch_raw_ocr_rows())
    # logger.info(f"Fetched {len(rows)} rows")

    rows_to_insert = []
    for row in rows:
        print(repr(row))

        # Initialize data with None to avoid KeyError
        data = {
            "invoice_number": None,
            "Date_of_issue": None,
            "seller_name": None,
            "seller_address": None,
            "seller_tax_id": None,
            "client_name": None,
            "client_address": None,
            "client_tax_id": None,
            "total_net": None,
            "total_vat": None,
            "total_gross": None,
        }

        data["invoice_number"] = extract(
            r"Invoice\s*no[:\s]+(\d+)", row.text
        )

        data["Date_of_issue"] = extract(
            r"Date of issue[:\s]*\n?([0-9/.-]+)", row.text
        )

        seller_block = extract(
            r"Seller:(.*?)(?=Client:)",
            repr(row.text),
            group=1
        )
        if seller_block:
            seller_block = seller_block.replace("\\n", " ").replace("\n", " ")
            # logger.info(f'seller_block: {seller_block}')
            
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
        if client_block:
            client_block = client_block.replace("\\n", " ").replace("\n", " ")
            # logger.info(f'client_block: {client_block}')
            
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
            data["total_net"] = str(normalize_amount(totals[-3]))
            data["total_vat"] = str(normalize_amount(totals[-2]))
            data["total_gross"] = str(normalize_amount(totals[-1]))

        # logger.info(f"Extracted Data: {data}")

        # Helper to ensure string or None
        def to_str(val):
            return str(val) if val is not None else None

        table_row = {
            "correlation_id": to_str(row.correlation_id),
            "file_name": to_str(row.file_name),
            "invoice_number": to_str(data["invoice_number"]),
            "Date_of_issue": to_str(data["Date_of_issue"]),
            "seller_name": to_str(data["seller_name"]),
            "seller_address": to_str(data["seller_address"]),
            "seller_tax_id": to_str(data["seller_tax_id"]),
            "client_name": to_str(data["client_name"]),
            "client_address": to_str(data["client_address"]),
            "client_tax_id": to_str(data["client_tax_id"]),
            "total_net": to_str(data["total_net"]),
            "total_vat": to_str(data["total_vat"]),
            "total_gross": to_str(data["total_gross"]),
        }

        rows_to_insert.append(table_row)
    
    logger.info(rows_to_insert)

    # insert into table
    bigquery_insert(rows_to_insert, f"{PROJECT_ID}.{DATASET}.{SUMMARY_TABLE}")

if __name__ == "__main__":
    run_transformer()