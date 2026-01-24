import pytest
from services.ocr.main import handle_message_async

@pytest.mark.asyncio
async def test_handle_message_async(mocker):
    message = mocker.Mock()
    message.data = b'{"gcs_path": "...", "file_name": "...", "correlation_id": "1"}'
    message.ack = mocker.Mock()

    await handle_message_async(message)

    message.ack.assert_called_once()