resource "google_project_service" "required_apis" {
  for_each = toset([
    "storage.googleapis.com",
    "pubsub.googleapis.com",
    "container.googleapis.com",
    "bigquery.googleapis.com",
    "aiplatform.googleapis.com",
    "artifactregistry.googleapis.com",
    "iam.googleapis.com"
  ])

  service = each.value
}