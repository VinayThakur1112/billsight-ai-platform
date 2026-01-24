from services.transform.main import extract

def test_extract_invoice_number():
    text = "Invoice no: 51295021"
    result = extract(r"Invoice\s*no[:\s]+(\d+)", text)
    assert result == "51295021"