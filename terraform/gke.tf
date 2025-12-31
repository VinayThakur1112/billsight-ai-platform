# GKE Cluster definition
resource "google_container_cluster" "primary" {
  name     = "billsight-gke"
  location = var.region

  remove_default_node_pool = true
  initial_node_count       = 1

  workload_identity_config {
    workload_pool = "${var.project_name}.svc.id.goog"
  }

  networking_mode = "VPC_NATIVE"
}

# node pool definition
resource "google_container_node_pool" "cpu_pool" {
  name       = "cpu_pool"
  cluster    = google_container_cluster.primary.name
  location   = var.region
  node_count = 1

  node_config {
    machine_type = "e2-standard-4"   # CPU / RAM
    disk_type    = "pd-balanced"      # pd-standard | pd-balanced | pd-ssd
    disk_size_gb = 30               # Disk size per node

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
    max_node_count = 3
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }
}