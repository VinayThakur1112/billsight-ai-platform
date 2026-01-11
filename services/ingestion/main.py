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


@app.post("/upload-bill")
async def upload_bill(file: UploadFile = File(...)):
    """
    Upload a bill file to the storage bucket and trigger 
    processing.

    This endpoint:
    - Accepts a file upload
    - Generates a unique path for the file in GCS based on 
    the current date
    - Uploads the file to the configured GCS bucket
    - Sets initial metadata for the file (processing state,
     version, etc.)
    - Publishes a message to Pub/Sub to trigger the extraction 
    pipeline

    Args:
        file (UploadFile): The bill document to upload.

    Returns:
        dict: detailed status and storage path of the uploaded 
        file.

    Raises:
        HTTPException: 500 error if any step of the upload or 
        publication fails.
    """
    try:
        logger.info("Uploading bill: %s", file.filename)
        # Create path with date prefix
        now = datetime.now()
        path = (
            f"bills/{now.year}/{now.month:02}/{now.day:02}/"
            f"{uuid.uuid4()}_{file.filename}"
            )

        blob = bucket.blob(path)

        # Upload file
        blob.upload_from_file(
            file.file, content_type=file.content_type)

        # Add metadata
        blob.metadata = {
            "processing_state": "uploaded",
            "last_updated": now.strftime("%Y%m%d%H%M"),
            "retry_count": "0",
            "pipeline_version": PIPELINE_VERSION
        }
        blob.patch()

        logger.info("Bill uploaded to GCS: %s", path)

        # Publish Pub/Sub message
        message = {
            "gcs_path": f"gs://{BUCKET_NAME}/{path}",
            "file_name": file.filename,
            "correlation_id": str(uuid.uuid4())
        }
        publisher.publish(
            topic_path, json.dumps(message).encode("utf-8"))

        logger.info(f"Published Pub/Sub message \
                    for: {file.filename}")

        return {"status": "success", "path": path}

    except Exception as e:
        logger.error(f"Failed to upload bill \
                     {file.filename}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))