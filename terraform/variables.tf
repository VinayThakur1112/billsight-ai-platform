variable "project_id" {
  type        = string
  description = "GCP project ID"
}

variable "region" {
  type        = string
  description = "Primary GCP region"
  default     = "us-central1"
}

variable "environment" {
  type        = string
  description = "Environment name (dev/staging/prod)"
}