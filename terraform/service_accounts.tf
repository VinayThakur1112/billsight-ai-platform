resource "google_service_account" "ingestion" {
  account_id   = "ingestion-sa"
  display_name = "Ingestion Service Account"
}

resource "google_service_account" "ocr" {
  account_id   = "ocr-sa"
  display_name = "OCR Service Account"
}

resource "google_service_account" "postprocess" {
  account_id   = "postprocess-sa"
  display_name = "Postprocess Service Account"
}