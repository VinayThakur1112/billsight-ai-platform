terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 5.0"
    }
  }
}


provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}


########################
# VARIABLES
########################
variable "project_id" {
    default = "billingsight-ai-project"
}
variable "region" {
  default = "asia-south1"
}
variable "zone" {
  default = "asia-south1-a"
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
    "iam.googleapis.com",
    "documentai.googleapis.com"
  ])

  service = each.value
}


########################
# VPC NETWORK
########################
# resource "google_compute_network" "vpc" {
#   name                    = "ocr-vpc"
#   auto_create_subnetworks = false
# }

# resource "google_compute_subnetwork" "private" {
#   name          = "ocr-private-subnet"
#   ip_cidr_range = "10.0.0.0/20"
#   region        = var.region
#   network       = google_compute_network.vpc.id
#   private_ip_google_access = true
# }


########################
# ARTIFACT REGISTRY
########################
resource "google_artifact_registry_repository" "billsight_repo" {
  provider      = google-beta
  location      = var.region
  repository_id = "billsight-repo"
  description   = "Docker repository for billsight project"
  format        = "DOCKER"
  project       = var.project_id
}

data "google_client_config" "default" {}

provider "kubernetes" {
  host                   = "https://${google_container_cluster.gke.endpoint}"
  token                  = data.google_client_config.default.access_token
  cluster_ca_certificate = base64decode(
    google_container_cluster.gke.master_auth[0].cluster_ca_certificate
  )
}


########################
# GOOGLE SERVICE ACCOUNT
########################
resource "google_service_account" "ingestion" {
  account_id   = "ingestion-gsa"
  display_name = "Ingestion Service Account"
}
resource "google_service_account" "ocr" {
  account_id   = "ocr-gsa"
  display_name = "ocr Service Account"
}
resource "google_service_account" "postprocess" {
  account_id   = "postprocess-gsa"
  display_name = "postprocess Service Account"
}
resource "google_service_account" "cicd" {
  account_id   = "cicd-gsa"
  display_name = "CI/CD Service Account"
}

########################
resource "google_project_service" "gke" {
  project = var.project_id
  service = "container.googleapis.com"
}


########################
# GKE PRIVATE CLUSTER
########################
resource "google_container_cluster" "gke" {
  name     = "billsight-gke-cluster"
  location = var.zone

  depends_on = [google_project_service.gke]

  networking_mode = "VPC_NATIVE"
  remove_default_node_pool = true
  initial_node_count       = 1

  # network    = google_compute_network.vpc.id
  # subnetwork = google_compute_subnetwork.private.id

  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  # private_cluster_config {
  #   enable_private_nodes    = true
  #   enable_private_endpoint = false
  #   master_ipv4_cidr_block  = "172.16.0.0/28"
  # }
}

## costly version
# resource "google_container_node_pool" "gke_pool" {
#   name       = "gke-pool"
#   location   = var.zone
#   cluster    = google_container_cluster.gke.name
#   node_count = 1

#   node_config {
#     machine_type   = "e2-standard-4"
#     oauth_scopes   = ["https://www.googleapis.com/auth/cloud-platform"]
#     disk_type    = "pd-balanced" 
#     disk_size_gb = 20  
#     service_account = google_service_account.ingestion.email

#     metadata = {
#       disable-legacy-endpoints = "true"
#     }
#   }

#   autoscaling {
#     min_node_count = 1
#     max_node_count = 1
#   }

#   management {
#     auto_repair  = true
#     auto_upgrade = true
#   }
# }
# cost effective version
resource "google_container_node_pool" "gke_pool" {
  name     = "gke-pool"
  location = var.zone
  cluster  = google_container_cluster.gke.name

  node_count = 1

  node_config {
    machine_type = "e2-small"   # ✅ BIG SAVING
    disk_type    = "pd-standard"
    disk_size_gb = 12

    service_account = google_service_account.ingestion.email
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]

    metadata = {
      disable-legacy-endpoints = "true"
    }
  }

  autoscaling {
    min_node_count = 1
    max_node_count = 1
  }
}

# iam binding
resource "google_service_account_iam_member" "ingestion_wi" {
  service_account_id = google_service_account.ingestion.name
  role               = "roles/iam.workloadIdentityUser"

  member = "serviceAccount:${var.project_id}.svc.id.goog[default/ingestion-ksa]"

  depends_on = [google_container_cluster.gke]
}

resource "google_service_account_iam_member" "ocr_wi" {
  service_account_id = google_service_account.ocr.name
  role               = "roles/iam.workloadIdentityUser"

  member = "serviceAccount:${var.project_id}.svc.id.goog[default/ocr-ksa]"

  depends_on = [google_container_cluster.gke]
}


########################
# Kubernetes Service Accounts
########################
resource "kubernetes_service_account_v1" "ingestion" {
  depends_on = [google_container_cluster.gke]
  metadata {
    name      = "ingestion-ksa"
    namespace = "default"

    annotations = {
      "iam.gke.io/gcp-service-account" = google_service_account.ingestion.email
    }
  }
}

resource "kubernetes_service_account_v1" "ocr" {
  depends_on = [google_container_cluster.gke]
  metadata {
    name      = "ocr-ksa"
    namespace = "default"

    annotations = {
      "iam.gke.io/gcp-service-account" = google_service_account.ocr.email
    }
  }
}

resource "kubernetes_service_account_v1" "postprocess" {
  depends_on = [google_container_cluster.gke]
  metadata {
    name      = "postprocess-ksa"
    namespace = "default"

    annotations = {
      "iam.gke.io/gcp-service-account" = google_service_account.postprocess.email
    }
  }
}


########################
# Kubernetes config map
########################
resource "kubernetes_config_map_v1" "app_config" {
  metadata {
    name      = "app-config-v1"
    namespace = "default"
  }

  data = {
    LOG_LEVEL           = "INFO"
    PROJECT_ID          = var.project_id
    BUCKET_NAME         = google_storage_bucket.buckets.name
    PUBSUB_TOPIC        = google_pubsub_topic.bill_upload.name
    PUBSUB_SUBSCRIPTION = google_pubsub_subscription.ingestion_sub.name
    PIPELINE_VERSION    = "v1"
    BQ_DATASET          = google_bigquery_dataset.ocr.dataset_id
    BQ_TABLE            = google_bigquery_table.billing_ocr_data.table_id
    DOC_AI_PROCESSOR    = google_document_ai_processor.bills_ocr.name
    DOC_AI_LOCATION     = google_document_ai_processor.bills_ocr.location
  }
}


########################
# CLOUD STORAGE BUCKET
########################
resource "google_storage_bucket" "buckets" {
  name          = "${var.project_id}-bills"
  location      = var.region
  force_destroy = true

  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }
}


########################
# PUB/SUB TOPIC
########################
resource "google_pubsub_topic" "bill_upload" {
  name = "bill-upload-events"
}

resource "google_pubsub_topic" "dead_letter" {
  name = "bill-dead-letter-events"
}

resource "google_pubsub_subscription" "ingestion_sub" {
  name  = "bill-ingestion-sub-v3"
  topic = google_pubsub_topic.bill_upload.name
  project = var.project_id

  ack_deadline_seconds = 30

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.dead_letter.id
    max_delivery_attempts = 5
  }
}


########################
# BIGQUERY
########################
resource "google_bigquery_dataset" "ocr" {
  dataset_id = "billsight_ocr"
  location   = var.region
}


resource "google_bigquery_table" "ocr_table" {
  dataset_id = google_bigquery_dataset.ocr.dataset_id
  table_id   = "extracted_bills"
  schema     = <<EOF
[
  {"name":"id","type":"STRING","mode":"REQUIRED"},
  {"name":"text","type":"STRING","mode":"NULLABLE"},
  {"name":"created_at","type":"TIMESTAMP","mode":"NULLABLE"}
]
EOF
}

resource "google_bigquery_table" "billing_ocr_data" {
  dataset_id = google_bigquery_dataset.ocr.dataset_id
  table_id   = "billing_ocr_data"
  deletion_protection = false
  schema     = <<EOF
[
  {"name":"correlation_id","type":"STRING","mode":"REQUIRED"},
  {"name":"file_name","type":"STRING","mode":"NULLABLE"},
  {"name":"text","type":"STRING","mode":"NULLABLE"},
  {"name":"page_count","type":"STRING","mode":"NULLABLE"},
  {"name":"model_used","type":"STRING","mode":"NULLABLE"},
  {
    "name":"logtime",
    "type":"TIMESTAMP",
    "mode":"NULLABLE", 
    "defaultValueExpression":"CURRENT_TIMESTAMP()"
  }, 
  {"name":"processed_at","type":"TIMESTAMP","mode":"NULLABLE"},
  {"name":"processed_by","type":"STRING","mode":"NULLABLE"}
]
EOF
}

resource "google_bigquery_table" "billsight_invoice_summary" {
  dataset_id = google_bigquery_dataset.ocr.dataset_id
  table_id   = "billsight_invoice_summary"
  deletion_protection = false
  schema     = <<EOF
[
  {"name":"correlation_id","type":"STRING","mode":"REQUIRED"},
  {"name":"file_name","type":"STRING","mode":"NULLABLE"},
  {"name":"invoice_number","type":"STRING","mode":"NULLABLE"},
  {"name":"Date_of_issue","type":"STRING","mode":"NULLABLE"},
  {"name":"seller_name","type":"STRING","mode":"NULLABLE"},
  {"name":"seller_address","type":"STRING","mode":"NULLABLE"},
  {"name":"seller_tax_id","type":"STRING","mode":"NULLABLE"},
  {"name":"client_name","type":"STRING","mode":"NULLABLE"},
  {"name":"client_address","type":"STRING","mode":"NULLABLE"},
  {"name":"client_tax_id","type":"STRING","mode":"NULLABLE"},
  {"name":"total_net","type":"STRING","mode":"NULLABLE"},
  {"name":"total_vat","type":"STRING","mode":"NULLABLE"},
  {"name":"total_gross","type":"STRING","mode":"NULLABLE"},
  {
    "name":"logtime",
    "type":"TIMESTAMP",
    "mode":"NULLABLE", 
    "defaultValueExpression":"CURRENT_TIMESTAMP()"
  }, 
  {"name":"processed_at","type":"TIMESTAMP","mode":"NULLABLE"},
  {"name":"processed_by","type":"STRING","mode":"NULLABLE"}
]
EOF
}

resource "google_bigquery_table" "billsight_invoice_items_list" {
  dataset_id = google_bigquery_dataset.ocr.dataset_id
  table_id   = "billsight_invoice_items_list"
  deletion_protection = false
  schema     = <<EOF
[
  {"name":"correlation_id","type":"STRING","mode":"REQUIRED"},
  {"name":"file_name","type":"STRING","mode":"NULLABLE"},
  {"name":"description","type":"STRING","mode":"NULLABLE"},
  {"name":"quantity","type":"STRING","mode":"NULLABLE"},
  {"name":"um","type":"STRING","mode":"NULLABLE"},
  {"name":"net_price","type":"STRING","mode":"NULLABLE"},
  {"name":"net_worth","type":"STRING","mode":"NULLABLE"},
  {"name":"vat","type":"STRING","mode":"NULLABLE"},
  {"name":"gross_worth","type":"STRING","mode":"NULLABLE"},
  {
    "name":"logtime",
    "type":"TIMESTAMP",
    "mode":"NULLABLE", 
    "defaultValueExpression":"CURRENT_TIMESTAMP()"
  }, 
  {"name":"processed_at","type":"TIMESTAMP","mode":"NULLABLE"},
  {"name":"processed_by","type":"STRING","mode":"NULLABLE"}
]
EOF
}


########################
# IAM BINDINGS
########################
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

resource "google_project_iam_member" "ocr_pubsub" {
  project = var.project_id
  role   = "roles/pubsub.subscriber"
  member = "serviceAccount:${google_service_account.ocr.email}"
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

# access to GCP service accounts to Artifact Registry
resource "google_project_iam_member" "gke_artifact_registry_pull" {
  project = var.project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${google_service_account.ingestion.email}"
}

# access to GCP service accounts to GCS bucket
resource "google_storage_bucket_iam_member" "ingestion_gcs_upload" {
  bucket = "${var.project_id}-bills"
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.ingestion.email}"
}

# access to GCP service accounts to Pub/Sub topic
resource "google_pubsub_topic_iam_member" "ingestion_pubsub_publish" {
  topic  = google_pubsub_topic.bill_upload.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${google_service_account.ingestion.email}"
}

# access to GCP service accounts to GCS bucket directly via IAM
resource "google_storage_bucket_iam_member" "ingestion_gcs_object_admin" {
  bucket = google_storage_bucket.buckets.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:ingestion-gsa@${var.project_id}.iam.gserviceaccount.com"
}

# access to GCP service accounts to Document AI API
resource "google_project_iam_member" "document_ai_access" {
  project = var.project_id
  role   = "roles/documentai.apiUser"
  member = "serviceAccount:${google_service_account.ocr.email}"
}

# access to GCP service accounts to BigQuery Dataset
resource "google_project_iam_member" "ocr_bq_editor" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.ocr.email}"
}

# access to GCP service accounts to BigQuery Dataset
resource "google_project_iam_member" "ocr_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.ocr.email}"
}

# access to CI/CD service account to Artifact Registry
resource "google_project_iam_member" "cicd_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.cicd.email}"
}
resource "google_project_iam_member" "cicd_developer" {
  project = var.project_id
  role    = "roles/container.developer"
  member  = "serviceAccount:${google_service_account.cicd.email}"
}
resource "google_project_iam_member" "cicd_cluster_viewer" {
  project = var.project_id
  role    = "roles/container.clusterViewer"
  member  = "serviceAccount:${google_service_account.cicd.email}"
}
resource "google_project_iam_member" "cicd_wi_user" {
  project = var.project_id
  role    = "roles/iam.workloadIdentityUser"
  member  = "serviceAccount:${google_service_account.cicd.email}"
}


########################
# DOCUMENT AI PROCESSOR
########################
resource "google_project_service" "documentai" {
  project = var.project_id
  service = "documentai.googleapis.com"
}

resource "google_document_ai_processor" "bills_ocr" {
  project      = var.project_id
  location     = "us"
  display_name = "ocr-processor"
  type         = "OCR_PROCESSOR"

  depends_on = [
    google_project_service.documentai
  ]
}

########################
# CICD setup
########################
# resource "google_iam_workload_identity_pool" "github_pool" {
#   provider                  = google-beta
#   project                   = var.project_id
#   location                  = var.region
#   workload_identity_pool_id = "github-pool"
#   display_name              = "GitHub Actions Pool"
# }

# resource "google_iam_workload_identity_pool_provider" "github_provider" {
#   provider                           = google-beta
#   project                            = var.project_id
#   location                           = var.region
#   workload_identity_pool_id          = google_iam_workload_identity_pool.github_pool.workload_identity_pool_id
#   workload_identity_pool_provider_id = "github"

#   display_name = "GitHub Provider"
#   oidc {
#     issuer_uri = "https://token.actions.githubusercontent.com"
#   }

#   attribute_mapping = {
#     "google.subject"       = "assertion.sub"
#     "attribute.repository" = "assertion.repository"
#   }
# }

# resource "google_service_account_iam_member" "github_wif_binding" {
#   service_account_id = "projects/${var.project_id}/serviceAccounts/cicd-gsa@${var.project_id}.iam.gserviceaccount.com"
#   role               = "roles/iam.workloadIdentityUser"

#   member = "principalSet://iam.googleapis.com/projects/${data.google_project.project.number}/locations/global/workloadIdentityPools/${google_iam_workload_identity_pool.github_pool.workload_identity_pool_id}/attribute.repository/${var.github_org}/${var.github_repo}"
# }



########################
# OUTPUTS
########################
output "gke_cluster_name" {
  value = google_container_cluster.gke.name
}

# output "private_api_ip" {
#   value = google_compute_address.private_lb.address
# }

output "bucket_name" {
  value = google_storage_bucket.buckets.name
}

output "doc_ai_processor_id" {
  value = google_document_ai_processor.bills_ocr.name
}

# output "workload_identity_provider" {
#   value = "projects/${data.google_project.project.number}/locations/global/workloadIdentityPools/${google_iam_workload_identity_pool.github_pool.workload_identity_pool_id}/providers/${google_iam_workload_identity_pool_provider.github_provider.workload_identity_pool_provider_id}"
# }