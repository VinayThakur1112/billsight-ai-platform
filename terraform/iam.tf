resource "google_project_iam_member" "ingestion_pubsub" {
  role   = "roles/pubsub.subscriber"
  member = "serviceAccount:${google_service_account.ingestion.email}"
}

resource "google_project_iam_member" "ingestion_gcs" {
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.ingestion.email}"
}

resource "google_project_iam_member" "ocr_vertex" {
  role   = "roles/aiplatform.user"
  member = "serviceAccount:${google_service_account.ocr.email}"
}

resource "google_project_iam_member" "ocr_gcs" {
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.ocr.email}"
}

resource "google_project_iam_member" "postprocess_bq" {
  role   = "roles/bigquery.dataEditor"
  member = "serviceAccount:${google_service_account.postprocess.email}"
}