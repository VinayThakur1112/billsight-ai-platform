import json
import os
import signal
from google.cloud import pubsub_v1
from google.cloud import storage, documentai, bigquery
from services.common.logging import get_logger
from dotenv import load_dotenv
load_dotenv()

logger = get_logger(__name__)

PROJECT_ID = os.getenv("PROJECT_ID")
BUCKET_NAME = os.getenv("BUCKET_NAME")
LOCATION = os.getenv("DOC_AI_LOCATION")
PROCESSOR_ID = os.getenv("DOC_AI_PROCESSOR")
BQ_DATASET = os.getenv("BQ_DATASET")
BQ_TABLE = os.getenv("BQ_TABLE")
SUBSCRIPTION_ID = os.getenv("PUBSUB_SUBSCRIPTION")

logger.info(f"PROJECT_ID id: {PROJECT_ID}")
    

subscriber = pubsub_v1.SubscriberClient()
subscription_path = subscriber.subscription_path(
    PROJECT_ID, SUBSCRIPTION_ID
)

storage_client = storage.Client()
docai_client = documentai.DocumentProcessorServiceClient()
bq_client = bigquery.Client()

shutdown = False

def signal_handler(sig, frame):
    global shutdown
    shutdown = True



# Register signal handlers for graceful shutdown
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


def callback(message: pubsub_v1.subscriber.message.Message):
    try:
        logger.info(message.data.decode("utf-8"))
        payload = json.loads(message.data.decode("utf-8"))
        logger.info(f"Received message: {payload}")
        process_message(payload)
        message.ack()
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        message.nack()


class BusinessProcessingError(Exception):
    pass

def process_message(message):
    """
    Process a Pub/Sub message triggering OCR on a document.

    This function:
    1. Parses the Pub/Sub message.
    2. Downloads the file from GCS.
    3. Checks for idempotency (skips if already processed).
    4. Sends the document to Google Cloud Document AI for OCR.
    5. Extracts text and page count.
    6. Stores the results in BigQuery.
    7. Updates the GCS object metadata to mark as processed.

    Args:
        message (str): The Pub/Sub message data (JSON string).
    """
    try:
        logger.info("Received Pub/Sub message for processing")
        payload = json.loads(message)
        gcs_path = payload["gcs_path"]
        correlation_id = payload["correlation_id"]

        bucket_name, blob_path = gcs_path.replace(
            "gs://", "").split("/", 1)
        
        logger.info(
            f"Processing file from GCS: {gcs_path}")
        logger.info(
            f"Bucket name: {bucket_name}")
        logger.info(
            f"Blob path: {blob_path}")
        
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        metadata = blob.metadata or {}

        try:
            if metadata.get("processing_state") == "processed" \
                or metadata.get("processing_state") == "failed":
                logger.info(
                    f"Skipping already processed file: \
                    {payload.get('file_name')}")
                return  # idempotent safe exit

            # ---- Document AI ----
            logger.info(
                f"Starting Document AI processing for: \
                {payload.get('file_name')}")

            name = docai_client.processor_path(
                PROJECT_ID, LOCATION, PROCESSOR_ID)

            request = documentai.ProcessRequest(
                name=name,
                gcs_document=documentai.GcsDocument(
                    gcs_uri=gcs_path,
                    mime_type="image/jpeg"
                )
            )

            try:
                result = docai_client.process_document(
                    request=request)
            except Exception as e:
                logger.error(
                    f"Failed to process document: {str(e)}")
                raise BusinessProcessingError(
                    "Document AI processing failed") from e

            document = result.document

            # ---- Transform Output ----
            row = {
                "correlation_id": correlation_id,
                "file_name": payload["file_name"],
                "text": document.text,
                "page_count": len(document.pages)
            }

            # ---- Write to BigQuery ----
            logger.info(f"Inserting results into BigQuery \
                for: {payload.get('file_name')}")

            table_id = f"{PROJECT_ID}.{BQ_DATASET}.{BQ_TABLE}"
            errors = bq_client.insert_rows_json(table_id, [row])
            if errors:
                raise BusinessProcessingError(
                    f"BigQuery insert failed: {errors}")

            # ---- Update Metadata ----
            metadata.update({"processing_state": "processed"})
            blob.metadata = metadata
            blob.patch()
            logger.info(f"Successfully processed and updated \
                metadata for: {payload.get('file_name')}")

        except BusinessProcessingError as e:
            retry_count = int(metadata.get("retry_count", "0"))

            if retry_count >= 3:
                metadata.update({"processing_state": "failed"})
            else:
                metadata.update({
                    "processing_state": "retry",
                    "retry_count": str(retry_count + 1)
                })
            blob.metadata = metadata
            blob.patch()
            logger.warning(f"Failed to process and updated \
                metadata for: {payload.get('file_name')}")
            return

    except Exception as e:
        logger.error(
            f"Error processing message for file \
            {json.loads(message).get('file_name', 'unknown')}: \
            {str(e)}")
        # Re-raising allows the Pub/Sub subscription to 
        # retry if configured
        raise

def main():
    streaming_pull_future = subscriber.subscribe(
        subscription_path, callback=callback
    )
    logger.info("OCR Worker started, listening for messages...")

    with subscriber:
        try:
            streaming_pull_future.result()
        except Exception as e:
            streaming_pull_future.cancel()
            raise e


if __name__ == "__main__":
    main()