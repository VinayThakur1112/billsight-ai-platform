import pytest
from services.common.models import PubSubIngestionMessage

def test_valid_pubsub_message():
    msg = {
        "gcs_path": "gs://bucket/file.pdf",
        "file_name": "file.pdf",
        "correlation_id": "123"
    }
    model = PubSubIngestionMessage(**msg)
    assert model.file_name == "file.pdf"

def test_invalid_pubsub_message():
    with pytest.raises(Exception):
        PubSubIngestionMessage(
            gcs_path="gs://bucket/file.pdf"
        )