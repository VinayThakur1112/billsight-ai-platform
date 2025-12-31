resource "google_bigquery_dataset" "ocr" {
  dataset_id = "billsight_ocr"
  location   = var.region
}