import json
from unittest.mock import Mock
from services.ocr.main import process_message

def test_process_message_success(mocker):
    mock_docai = mocker.patch(
        "services.ocr.main.docai_client"
    )

    mock_result = Mock()
    mock_result.document.text = "Sample text"
    mock_result.document.pages = [1, 2]

    mock_docai.process_document.return_value = mock_result

    message = {
        "gcs_path": "gs://bucket/test.jpg",
        "file_name": "test.jpg",
        "correlation_id": "abc"
    }

    process_message(json.dumps(message))