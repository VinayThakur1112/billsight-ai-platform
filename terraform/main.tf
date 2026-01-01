terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

# variables
variable "project_id" {
  type        = string
  description = "GCP Project ID"
}

variable "project_name" {
  type        = string
  description = "billsight-ai-platform"
}

variable "region" {
  type        = string
  description = "Primary GCP region"
  default     = "asia-south1"
}

variable "environment" {
  type        = string
  description = "prod"
}

provider "google" {
  project = var.project_id
  region  = var.region
}


# enable api
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

resource "google_project_service" "gke" {
  project = var.project_id
  service = "container.googleapis.com"
}

# GCS Buckets
resource "google_storage_bucket" "buckets" {
  name          = "${var.project_name}-bills"
  location      = var.region
  force_destroy = true

  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }
}

# pubsub
resource "google_pubsub_topic" "bill_upload" {
  name = "bill-upload-events"
}

resource "google_pubsub_topic" "dead_letter" {
  name = "bill-dead-letter-events"
}

resource "google_pubsub_subscription" "ingestion_sub" {
  name  = "bill-ingestion-sub"
  topic = google_pubsub_topic.bill_upload.name

  ack_deadline_seconds = 30

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.dead_letter.id
    max_delivery_attempts = 5
  }
}

# BigQuery
resource "google_bigquery_dataset" "ocr" {
  dataset_id = "billsight_ocr"
  location   = var.region
}

# IAM
resource "google_project_iam_member" "ingestion_pubsub" {
  project = var.project_id
  role   = "roles/pubsub.subscriber"
  member = "serviceAccount:${google_service_account.ingestion.email}"
}

resource "google_project_iam_member" "ingestion_gcs" {
  project = var.project_id
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.ingestion.email}"
}

resource "google_project_iam_member" "ocr_vertex" {
  project = var.project_id
  role   = "roles/aiplatform.user"
  member = "serviceAccount:${google_service_account.ocr.email}"
}

resource "google_project_iam_member" "ocr_gcs" {
  project = var.project_id
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.ocr.email}"
}

resource "google_project_iam_member" "postprocess_bq" {
  project = var.project_id
  role   = "roles/bigquery.dataEditor"
  member = "serviceAccount:${google_service_account.postprocess.email}"
}

# GKE Cluster
# GKE Cluster definition
resource "google_container_cluster" "primary" {
  name     = "billsight-gke"
  location = "asia-south1-a"
  project  = var.project_id

  depends_on = [google_project_service.gke]

  remove_default_node_pool = true
  initial_node_count       = 1

  workload_identity_config {
    workload_pool = "${var.project_name}.svc.id.goog"
  }

  networking_mode = "VPC_NATIVE"
}

# node pool definition
resource "google_container_node_pool" "cpu_pool" {
  name       = "cpu-pool"
  cluster    = google_container_cluster.primary.name
  location   = "asia-south1-a"
  node_count = 1
  project  = var.project_id

  node_config {
    machine_type = "e2-standard-4"   # CPU / RAM
    disk_type    = "pd-balanced"      # pd-standard | pd-balanced | pd-ssd
    disk_size_gb = 20               # Disk size per node

    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]

    labels = {
      environment = var.environment
    }

    metadata = {
      disable-legacy-endpoints = "true"
    }
  }

  autoscaling {
    min_node_count = 1
    max_node_count = 1
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }
}

# iam binding
resource "google_service_account_iam_binding" "ingestion_wi" {
  service_account_id = google_service_account.ingestion.name
  role               = "roles/iam.workloadIdentityUser"

  members = [
    "serviceAccount:${var.project_name}.svc.id.goog[default/ingestion-sa]"
  ]

  depends_on = [google_container_cluster.primary]
}

# service accounts
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


# artifact registry
resource "google_artifact_registry_repository" "billsight_repo" {
  provider      = google
  location      = var.region
  repository_id = "billsight-repo"
  description   = "Docker repository for billsight project"
  format        = "DOCKER"
  project       = var.project_name
}

provider "kubernetes" {
  host                   = "https://${google_container_cluster.primary.endpoint}"
  token                  = data.google_client_config.default.access_token
  cluster_ca_certificate = base64decode(
    google_container_cluster.primary.master_auth[0].cluster_ca_certificate
  )
}

data "google_client_config" "default" {}

resource "kubernetes_service_account_v1" "primary" {
  depends_on = [google_container_cluster.primary]
  metadata {
    name      = "ingestion-ksa"
    namespace = "default"

    annotations = {
      "iam.gke.io/gcp-service-account" = google_service_account.ingestion.email
    }
  }
}

resource "kubernetes_service_account_v1" "ocr" {
  depends_on = [google_container_cluster.primary]
  metadata {
    name      = "ocr-ksa"
    namespace = "default"

    annotations = {
      "iam.gke.io/gcp-service-account" = google_service_account.ocr.email
    }
  }
}

resource "kubernetes_service_account_v1" "postprocess" {
  depends_on = [google_container_cluster.primary]
  metadata {
    name      = "postprocess-ksa"
    namespace = "default"

    annotations = {
      "iam.gke.io/gcp-service-account" = google_service_account.postprocess.email
    }
  }
}

# access to GCP service accounts to GCS bucket
resource "google_storage_bucket_iam_member" "ingestion_gcs_upload" {
  bucket = "${var.project_name}-bills"
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.ingestion.email}"
}

# access to GCP service accounts to Pub/Sub topic
resource "google_pubsub_topic_iam_member" "ingestion_pubsub_publish" {
  topic  = google_pubsub_topic.bill_upload.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${google_service_account.ingestion.email}"
}

# Kubernetes Config Map
resource "kubernetes_config_map_v1" "app_config" {
  metadata {
    name      = "app-config-v1"
    namespace = "default"
  }

  data = {
    LOG_LEVEL           = "INFO"
    PROJECT_ID          = "billsight-ai-platform"
    BUCKET_NAME         = "billsight-ai-platform-bills"
    PUBSUB_TOPIC        = "bill-upload-events"
    PIPELINE_VERSION    = "v1"
  }
}

# Grant GKE nodes permission to pull images from Artifact Registry
resource "google_artifact_registry_repository_iam_member" "gke_pull_images" {
  project    = var.project_name
  location   = var.region
  repository = "billsight-repo"

  role   = "roles/artifactregistry.reader"
  member = "serviceAccount:${var.project_id}-compute@developer.gserviceaccount.com"
}