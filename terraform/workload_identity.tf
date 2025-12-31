# workload_identity.tf

resource "google_service_account_iam_binding" "ingestion_wi" {
  service_account_id = google_service_account.ingestion.name
  role               = "roles/iam.workloadIdentityUser"

  members = [
    "serviceAccount:${var.project_name}.svc.id.goog[default/ingestion-ksa]"
  ]
}