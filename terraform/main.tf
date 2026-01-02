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

########################
# SERVICE ACCOUNT
########################
resource "google_service_account" "gke_sa" {
  account_id   = "gke-ocr"
  display_name = "GKE OCR Workload Identity"
}

########################
# GKE PRIVATE CLUSTER
########################
resource "google_container_cluster" "gke" {
  name     = "ocr-gke"
  location = var.region

  networking_mode = "VPC_NATIVE"
  remove_default_node_pool = true
  initial_node_count       = 1

  network    = google_compute_network.vpc.id
  subnetwork = google_compute_subnetwork.private.id

  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = false
    master_ipv4_cidr_block  = "172.16.0.0/28"
  }
}

resource "google_container_node_pool" "primary_nodes" {
  name       = "ocr-nodepool"
  location   = var.region
  cluster    = google_container_cluster.gke.name
  node_count = 3

  node_config {
    machine_type   = "e2-standard-4"
    oauth_scopes   = ["https://www.googleapis.com/auth/cloud-platform"]
    service_account = google_service_account.gke_sa.email
  }
}

########################
# CLOUD STORAGE BUCKET
########################
resource "google_storage_bucket" "bills" {
  name          = "${var.project_id}-bills"
  location      = var.region
  force_destroy = true
}

########################
# PUB/SUB TOPIC
########################
resource "google_pubsub_topic" "ocr_topic" {
  name = "ocr-topic"
}

########################
# BIGQUERY
########################
resource "google_bigquery_dataset" "ocr" {
  dataset_id = "ocr_data"
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

########################
# CLOUD RUN (TRIGGER ENTRYPOINT)
########################
resource "google_service_account" "cloudrun_sa" {
  account_id   = "run-trigger"
  display_name = "Cloud Run trigger service account"
}

resource "google_cloud_run_v2_service" "trigger" {
  name     = "ocr-trigger"
  location = var.region
  ingress  = "INGRESS_INTERNAL_ONLY"

  template {
    service_account = google_service_account.cloudrun_sa.email
    scaling { max_instance_count = 1 }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/ocr-repo/trigger:latest"
      env {
        name  = "API_INTERNAL_IP"
        value = google_compute_forwarding_rule.private_api.ip_address
      }
    }

    vpc_access {
      connector = google_vpc_access_connector.serverless.id
      egress    = "ALL_TRAFFIC"
    }
  }
}

########################
# VPC CONNECTOR
########################
resource "google_vpc_access_connector" "serverless" {
  name   = "run-connector"
  region = var.region
  network = google_compute_network.vpc.name
  ip_cidr_range = "10.8.0.0/28"
}

########################
# INTERNAL LOAD BALANCER (PRIVATE IP)
########################
resource "google_compute_address" "private_lb" {
  name   = "ocr-private-ip"
  region = var.region
  subnetwork = google_compute_subnetwork.private.id
}

resource "google_compute_forwarding_rule" "private_api" {
  name        = "ocr-internal-forward"
  region      = var.region
  ip_address  = google_compute_address.private_lb.address
  load_balancing_scheme = "INTERNAL"
  target      = google_compute_region_backend_service.api.id
  network     = google_compute_network.vpc.id
  subnetwork  = google_compute_subnetwork.private.id
}

resource "google_compute_region_backend_service" "api" {
  name     = "ocr-api-backend"
  region   = var.region
  protocol = "HTTP"
  backend {
    group = google_compute_region_network_endpoint_group.gke_neg.id
  }
}

resource "google_compute_region_network_endpoint_group" "gke_neg" {
  name                  = "ocr-neg"
  region                = var.region
  network_endpoint_type = "GCE_VM_IP_PORT"
}

########################
# IAM BINDINGS
########################
resource "google_project_iam_member" "vertex" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.gke_sa.email}"
}

resource "google_project_iam_member" "run_invoker" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.cloudrun_sa.email}"
}

########################
# OUTPUTS
########################
output "gke_cluster_name" {
  value = google_container_cluster.gke.name
}

output "private_api_ip" {
  value = google_compute_address.private_lb.address
}

output "bucket_name" {
  value = google_storage_bucket.bills.name
}