"""
Bill Ingestion Service

This module provides a FastAPI application for processing bill 
uploads.
It handles:
1. Receiving files via HTTP POST requests
2. Uploading files to Google Cloud Storage (GCS) with organized 
paths
3. Attaching metadata to the GCS objects
4. Publishing notification messages to Google Cloud Pub/Sub for 
downstream processing
"""

import json
from fastapi import FastAPI, File, UploadFile, HTTPException
from google.cloud import storage, pubsub_v1
from datetime import datetime
import uuid
import os
import asyncio
from services.ingestion.metrics import (
    processing_latency,
    message_counter,
    failure_counter
)
import time
from services.common.logging import get_logger
logger = get_logger(__name__)

from dotenv import load_dotenv
load_dotenv()



PROJECT_ID = os.getenv("PROJECT_ID")
BUCKET_NAME = os.getenv("BUCKET_NAME")
PUBSUB_TOPIC = os.getenv("PUBSUB_TOPIC")
PIPELINE_VERSION = os.getenv("PIPELINE_VERSION")


# Initialize FastAPI app
app = FastAPI()

# Initialize GCS client
storage_client = storage.Client()
bucket = storage_client.bucket(BUCKET_NAME)

# Initialize Pub/Sub client
publisher = pubsub_v1.PublisherClient()
# Construct the full Pub/Sub topic path
topic_path = publisher.topic_path(
    os.getenv("PROJECT_ID"), PUBSUB_TOPIC)


# -------------------------------
# Blocking functions (SYNC)
# -------------------------------
def _sync_upload_to_gcs(file: UploadFile) -> dict:
    """
    Synchronously uploads a file to Google Cloud Storage.

    Args:
        file (UploadFile): The file to upload.

    Returns:
        dict: A dictionary containing the GCS path, file name, 
        and a correlation ID.
    """
    logger.info("Starting synchronous upload to GCS for file: %s", 
                file.filename)
    now = datetime.now()
    path = (
        f"bills/{now.year}/{now.month:02}/{now.day:02}/"
        f"{uuid.uuid4()}_{file.filename}"
    )

    # Create a blob with the generated path
    blob = bucket.blob(path)

    # Upload the file content
    blob.upload_from_file(
        file.file,
        content_type=file.content_type
    )

    # Set metadata for downstream processing
    blob.metadata = {
        "processing_state": "uploaded",
        "last_updated": now.strftime("%Y%m%d%H%M"),
        "retry_count": "0",
        "pipeline_version": PIPELINE_VERSION
    }
    blob.patch()
    
    logger.info("Successfully uploaded file to GCS: gs://%s/%s", 
                BUCKET_NAME, path)

    return {
        "gcs_path": f"gs://{BUCKET_NAME}/{path}",
        "file_name": file.filename,
        "correlation_id": str(uuid.uuid4())
    }

def _sync_publish_pubsub(message: dict):
    """
    Synchronously publishes a message to a Pub/Sub topic.

    Args:
        message (dict): The message payload to publish.
    """
    logger.info("Publishing message to Pub/Sub: %s", message)
    publisher.publish(
        topic_path,
        json.dumps(message).encode("utf-8")
    )


# -------------------------------
# Async API Endpoint
# -------------------------------
@app.post("/upload-bill")
async def upload_bill(file: UploadFile = File(...)):
    """
    Endpoint to upload a bill.

    This endpoint:
    1. Uploads the file to GCS.
    2. Publishes a notification to Pub/Sub.

    Args:
        file (UploadFile): The bill file to upload.

    Returns:
        dict: Status and path information.
    """
    loop = asyncio.get_running_loop()
    start_time = time.time()
    try:
        logger.info("Uploading bill: %s", file.filename)

        # Run the upload in a separate thread to avoid 
        # blocking the event loop
        message = await loop.run_in_executor(
            None,
            _sync_upload_to_gcs,
            file
        )

        # Publish the message to Pub/Sub in a separate thread
        await loop.run_in_executor(
            None,
            _sync_publish_pubsub,
            message
        )

        logger.info("Bill processed successfully: %s", 
                    message["gcs_path"])
        
        # ------------------ Metrics ------------------
        message_counter.add(1, {"status": "success"})

        return {
            "status": "success",
            "path": message["gcs_path"],
            "correlation_id": message["correlation_id"]
        }

    except Exception as e:
        logger.exception("Failed to upload bill %s", 
                         file.filename)
        failure_counter.add(1, {"error_type": "unexpected"})
        message_counter.add(1, {"status": "failed"})
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        processing_latency.record(
            time.time() - start_time,
            {"processor": "document_ai"}
        )
    