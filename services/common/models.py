from pydantic import BaseModel, Field
from typing import Optional

class OCRResult(BaseModel):
    correlation_id: str
    file_name: str
    text: str
    page_count: int