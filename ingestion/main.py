from fastapi import FastAPI, File, UploadFile, HTTPException
from google.cloud import storage, pubsub_v1
from datetime import datetime
import uuid
import os
from common.logging import get_logger
logger = get_logger(__name__)

from dotenv import load_dotenv
load_dotenv()



PROJECT_ID = os.getenv("PROJECT_ID")
BUCKET_NAME = os.getenv("BUCKET_NAME")
PUBSUB_TOPIC = os.getenv("PUBSUB_TOPIC")
PIPELINE_VERSION = os.getenv("PIPELINE_VERSION")

app = FastAPI()

# Initialize GCS client
storage_client = storage.Client()
bucket = storage_client.bucket(BUCKET_NAME)

# Initialize Pub/Sub client
publisher = pubsub_v1.PublisherClient()
topic_path = publisher.topic_path(
    os.getenv("PROJECT_ID"), PUBSUB_TOPIC)


@app.post("/upload-bill")
async def upload_bill(file: UploadFile = File(...)):
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
            topic_path, str(message).encode("utf-8"))

        logger.info(f"Published Pub/Sub message \
                    for: {file.filename}")

        return {"status": "success", "path": path}

    except Exception as e:
        logger.error(f"Failed to upload bill \
                     {file.filename}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))