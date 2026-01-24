import json
from fastapi.testclient import TestClient
from services.ingestion.main import app

def test_upload_bill_e2e(mocker):
    # -----------------------------
    # Mock GCS
    # -----------------------------
    mock_storage_client = mocker.patch(
        "services.ingestion.main.storage.Client"
    )
    mock_bucket = mock_storage_client.return_value.bucket.return_value
    mock_blob = mock_bucket.blob.return_value

    # -----------------------------
    # Mock Pub/Sub
    # -----------------------------
    mock_publisher = mocker.patch(
        "services.ingestion.main.pubsub_v1.PublisherClient"
    )
    mock_publish = mock_publisher.return_value.publish

    client = TestClient(app)

    response = client.post(
        "/upload-bill",
        files={"file": ("bill.pdf", b"fake-data", "application/pdf")}
    )

    # -----------------------------
    # Assertions
    # -----------------------------
    assert response.status_code == 200

    mock_blob.upload_from_file.assert_called_once()
    mock_blob.patch.assert_called_once()
    mock_publish.assert_called_once()

    payload = json.loads(
        mock_publish.call_args[0][1].decode("utf-8")
    )

    assert "gcs_path" in payload
    assert payload["file_name"] == "bill.pdf"