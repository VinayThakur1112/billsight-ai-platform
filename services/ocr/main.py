import json
import os
import signal
import asyncio
from concurrent.futures import ThreadPoolExecutor
from google.cloud import pubsub_v1
from google.cloud import storage, documentai, bigquery
from services.common.logging import get_logger
from dotenv import load_dotenv
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential_jitter,
    retry_if_exception_type
)

# ------------------------------------------------------------
# Environment & Logging
# ------------------------------------------------------------
load_dotenv()
logger = get_logger(__spec__.name if __spec__ else __name__)

PROJECT_ID = os.getenv("PROJECT_ID")
BUCKET_NAME = os.getenv("BUCKET_NAME")
LOCATION = os.getenv("DOC_AI_LOCATION")
PROCESSOR_ID = os.getenv("DOC_AI_PROCESSOR")
BQ_DATASET = os.getenv("BQ_DATASET")
BQ_TABLE = os.getenv("BQ_TABLE")
SUBSCRIPTION_ID = os.getenv("PUBSUB_SUBSCRIPTION")

logger.info(f"PROJECT_ID id: {PROJECT_ID}")


MAX_WORKERS = int(os.getenv("MAX_WORKERS", "5"))
DOC_AI_CONCURRENCY = int(os.getenv("DOC_AI_CONCURRENCY", "2"))
    
# ------------------------------------------------------------
# GCP Clients (blocking SDKs)
# ------------------------------------------------------------
subscriber = pubsub_v1.SubscriberClient()
subscription_path = subscriber.subscription_path(
    PROJECT_ID, SUBSCRIPTION_ID
)

logger.info(f"Subscription path: {subscription_path}")

storage_client = storage.Client()
docai_client = documentai.DocumentProcessorServiceClient()
bq_client = bigquery.Client()

# ------------------------------------------------------------
# Concurrency Controls
# ------------------------------------------------------------
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
docai_semaphore = asyncio.Semaphore(DOC_AI_CONCURRENCY)

# shutdown = False
shutdown_event = asyncio.Event()

# ------------------------------------------------------------
# Graceful Shutdown
# ------------------------------------------------------------
def signal_handler(sig, frame):
    logger.warning(f"Received shutdown signal: {sig}")
    # global shutdown
    # shutdown = True
    shutdown_event.set()

# Register signal handlers for graceful shutdown
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


# ------------------------------------------------------------
# Custom Exceptions
# ------------------------------------------------------------
class BusinessProcessingError(Exception):
    pass

def process_message_sync(message_data: str):
    process_message(message_data)



# ------------------------------------------------------------
# Document AI Call with Retry
# ------------------------------------------------------------
@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential_jitter(initial=1, max=10),
    retry=retry_if_exception_type(Exception),
    reraise=True
)
def call_document_ai_blocking(client, request):
    """
    Blocking call to Document AI with retry + backoff.
    """
    return client.process_document(request=request)


# ------------------------------------------------------------
# Core Business Logic
# ------------------------------------------------------------
def process_message(message: str):
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
    logger.info("Received Pub/Sub message for processing")
    payload = json.loads(message)

    gcs_path = payload["gcs_path"]
    correlation_id = payload["correlation_id"]

    bucket_name, blob_path = gcs_path.replace(
            "gs://", "").split("/", 1)

    logger.info(f"Processing file from GCS: {gcs_path}")
    logger.info(f"Bucket name: {bucket_name}")
    logger.info(f"Blob path: {blob_path}")

    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    metadata = blob.metadata or {}

    if metadata.get("processing_state") == "processed" \
        or metadata.get("processing_state") == "failed":
        logger.info(
                    f"Skipping already processed file: \
                    {payload.get('file_name')}")
        return
    
    try:
        # ------------------ Document AI ------------------
        logger.info(f"Starting Document AI processing for: \
                    {payload.get('file_name')}")
        
        name = docai_client.processor_path(
            PROJECT_ID, 'us', PROCESSOR_ID
            )
        
        logger.info(f"Document AI processor path: {name}")

        request = documentai.ProcessRequest(
            name=name,
            gcs_document=documentai.GcsDocument(
                gcs_uri=gcs_path,
                mime_type="image/jpeg"
            )
        )

        logger.info(f"Document AI request: {request}")

        # result = docai_client.process_document(request=request)
        result = call_document_ai_blocking(docai_client, request)
        document = result.document
        
        # ------------------ Transform ------------------
        row = {
                "correlation_id": correlation_id,
                "file_name": payload["file_name"],
                "text": document.text,
                "page_count": len(document.pages)
            }
        
        # ------------------ BigQuery ------------------
        table_id = f"{PROJECT_ID}.{BQ_DATASET}.{BQ_TABLE}"
        errors = bq_client.insert_rows_json(table_id, [row])

        if errors:
            raise BusinessProcessingError(
                f"BigQuery insert failed: {errors}")
        

        # ------------------ Update Metadata -------------
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


# ------------------------------------------------------------
# Async Wrapper
# ------------------------------------------------------------
async def handle_message_async(
    message: pubsub_v1.subscriber.message.Message):
    
    loop = asyncio.get_running_loop()
    loop.create_task(handle_message_async(message))
    
    correlation_id = "unknown"

    try:
        payload = json.loads(message.data.decode("utf-8"))
        correlation_id = payload.get(
            "correlation_id", "unknown")

        logger.info(f"[{correlation_id}] Message received")

        async with docai_semaphore:
            await loop.run_in_executor(
                executor,
                process_message,
                message.data.decode("utf-8")
            )

        message.ack()
        logger.info(f"[{correlation_id}] Message ACKed")

    except Exception:
        logger.exception(
            f"[{correlation_id}] Message failed, NACKing")
        message.nack()


# ------------------------------------------------------------
# Pub/Sub Callback Bridge
# ------------------------------------------------------------
def callback(message):
    asyncio.get_event_loop().create_task(
        handle_message_async(message)
    )


# ------------------------------------------------------------
# Async Main Loop
# ------------------------------------------------------------
async def main():
    streaming_pull_future = subscriber.subscribe(
        subscription_path,
        callback=callback
    )

    logger.info("OCR Worker started (async)")

    try:
        await shutdown_event.wait()
    finally:
        logger.warning("Shutting down worker...")
        streaming_pull_future.cancel()
        executor.shutdown(wait=True)
        subscriber.close()


# ------------------------------------------------------------
# Entry Point
# ------------------------------------------------------------
if __name__ == "__main__":
    asyncio.run(main())