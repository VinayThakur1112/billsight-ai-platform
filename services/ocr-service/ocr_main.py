import json
import os
from google.cloud import storage, documentai, bigquery

PROJECT_ID = os.getenv("PROJECT_ID")
BUCKET_NAME = os.getenv("BUCKET_NAME")
LOCATION = os.getenv("DOC_AI_LOCATION")
PROCESSOR_ID = os.getenv("DOC_AI_PROCESSOR")
BQ_DATASET = os.getenv("BQ_DATASET")
BQ_TABLE = os.getenv("BQ_TABLE")

storage_client = storage.Client()
docai_client = documentai.DocumentProcessorServiceClient()
bq_client = bigquery.Client()

def process_message(message):
    payload = json.loads(message)
    gcs_path = payload["gcs_path"]
    correlation_id = payload["correlation_id"]

    bucket_name, blob_path = gcs_path.replace(
        "gs://", "").split("/", 1)
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_path)

    metadata = blob.metadata or {}
    if metadata.get("processing_state") == "processed":
        return  # idempotent safe exit

    # ---- Document AI ----
    name = docai_client.processor_path(
        PROJECT_ID, LOCATION, PROCESSOR_ID)

    request = documentai.ProcessRequest(
        name=name,
        gcs_document=documentai.GcsDocument(
            gcs_uri=gcs_path,
            mime_type="image/jpeg"
        )
    )

    result = docai_client.process_document(request=request)
    document = result.document

    # ---- Transform Output ----
    row = {
        "correlation_id": correlation_id,
        "file_name": payload["file_name"],
        "text": document.text,
        "page_count": len(document.pages)
    }

    # ---- Write to BigQuery ----
    table_id = f"{PROJECT_ID}.{BQ_DATASET}.{BQ_TABLE}"
    bq_client.insert_rows_json(table_id, [row])

    # ---- Update Metadata ----
    metadata.update({
        "processing_state": "processed"
    })
    blob.metadata = metadata
    blob.patch()