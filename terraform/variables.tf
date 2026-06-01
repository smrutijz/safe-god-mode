variable "project_id" {
  type        = string
  description = "GCP project ID"
}

variable "region" {
  type        = string
  default     = "asia-southeast1"
  description = "GCP region"
}

variable "zone" {
  type        = string
  default     = "asia-southeast1-a"
  description = "GCP zone"
}

variable "machine_type" {
  type        = string
  default     = "e2-micro"
  description = "VM machine type"
}

variable "postgres_db_cidr" {
  type        = string
  description = "CIDR of the external PostgreSQL database e.g. 203.0.113.50/32"
}

variable "vm_service_account_email" {
  type        = string
  description = "Service account email attached to the VM"
}

variable "api_service_account_email" {
  type        = string
  description = "Service account email used by the FastAPI server to open IAP tunnels and inject SSH keys"
}
