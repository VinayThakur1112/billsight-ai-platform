resource "google_storage_bucket" "buckets" {
  for_each = {
    name       = "${var.project_name}-bills"
    # processed = "${var.project_name}-bills-processed-text"
    # archive   = "${var.project_name}-bills-archive"
  }

  name          = each.name
  location      = var.region
  force_destroy = true

  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }
}