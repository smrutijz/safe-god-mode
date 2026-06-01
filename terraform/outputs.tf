output "vm_name" {
  value       = google_compute_instance.agent_vm.name
  description = "Set as VM_NAME in your FastAPI .env"
}

output "zone" {
  value       = google_compute_instance.agent_vm.zone
  description = "Set as GCP_ZONE in your FastAPI .env"
}

output "project_id" {
  value       = var.project_id
  description = "Set as GCP_PROJECT in your FastAPI .env"
}
