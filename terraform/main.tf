terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

# ── VPC ────────────────────────────────────────────────────────────────────────

resource "google_compute_network" "vpc" {
  name                    = "prod-secure-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "private" {
  name                     = "private-mgmt-subnet"
  ip_cidr_range            = "10.0.1.0/24"
  region                   = var.region
  network                  = google_compute_network.vpc.id
  private_ip_google_access = true
}

# ── NAT (outbound internet for the private VM) ─────────────────────────────────

resource "google_compute_router" "router" {
  name    = "nat-router"
  region  = var.region
  network = google_compute_network.vpc.id
}

resource "google_compute_router_nat" "nat" {
  name                               = "outbound-nat"
  router                             = google_compute_router.router.name
  region                             = var.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"

  log_config {
    enable = true
    filter = "ERRORS_ONLY"
  }
}

# ── Firewall — INGRESS ─────────────────────────────────────────────────────────

# Allow SSH only from Google IAP proxy range
resource "google_compute_firewall" "allow_iap_ssh" {
  name      = "allow-iap-ssh-ingress"
  network   = google_compute_network.vpc.name
  direction = "INGRESS"
  priority  = 1000

  source_ranges = ["35.235.240.0/20"]
  target_tags   = ["secure-agent-vm"]

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}

# ── Firewall — EGRESS ──────────────────────────────────────────────────────────

# Deny all outbound traffic by default (safety net)
resource "google_compute_firewall" "deny_all_egress" {
  name      = "deny-all-egress"
  network   = google_compute_network.vpc.name
  direction = "EGRESS"
  priority  = 65000

  destination_ranges = ["0.0.0.0/0"]
  target_tags        = ["secure-agent-vm"]

  deny {
    protocol = "all"
  }
}

# Allow outbound to PostgreSQL only
resource "google_compute_firewall" "allow_postgres_egress" {
  name      = "allow-postgres-egress"
  network   = google_compute_network.vpc.name
  direction = "EGRESS"
  priority  = 1000

  destination_ranges = [var.postgres_db_cidr]
  target_tags        = ["secure-agent-vm"]

  allow {
    protocol = "tcp"
    ports    = ["5432"]
  }
}

# Allow outbound HTTPS (port 443) for Claude API + npm installs via Cloud NAT
# Scope this further with a Squid/Privoxy proxy on the VM for domain whitelisting
resource "google_compute_firewall" "allow_https_egress" {
  name      = "allow-https-egress"
  network   = google_compute_network.vpc.name
  direction = "EGRESS"
  priority  = 1001

  destination_ranges = ["0.0.0.0/0"]
  target_tags        = ["secure-agent-vm"]

  allow {
    protocol = "tcp"
    ports    = ["443"]
  }
}

# Allow outbound to Google APIs (used by Cloud NAT, metadata server, etc.)
resource "google_compute_firewall" "allow_google_apis_egress" {
  name      = "allow-google-apis-egress"
  network   = google_compute_network.vpc.name
  direction = "EGRESS"
  priority  = 999

  destination_ranges = ["199.36.153.8/30", "199.36.153.4/30"]
  target_tags        = ["secure-agent-vm"]

  allow {
    protocol = "tcp"
    ports    = ["443"]
  }
}

# ── VM ─────────────────────────────────────────────────────────────────────────

resource "google_compute_instance" "agent_vm" {
  name         = "secure-agent-vm"
  machine_type = var.machine_type
  zone         = var.zone
  tags         = ["secure-agent-vm"]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 20
      type  = "pd-standard"
    }
  }

  network_interface {
    network    = google_compute_network.vpc.id
    subnetwork = google_compute_subnetwork.private.id
    # No access_config block = no public IP
  }

  metadata = {
    # NOTE: enable-oslogin must remain FALSE (or unset).
    # The FastAPI app injects ephemeral SSH keys via instance metadata.
    # OS Login and metadata-based SSH keys are mutually exclusive in GCP —
    # enabling OS Login would silently ignore all ssh-keys metadata entries
    # and break the FastAPI key injection entirely.
    enable-oslogin = "FALSE"
  }

  service_account {
    email  = var.vm_service_account_email
    scopes = ["cloud-platform"]
  }
}

# ── IAM — API server permissions ───────────────────────────────────────────────

# Allow the FastAPI service account to open IAP tunnels to the VM
resource "google_iap_tunnel_instance_iam_member" "api_tunnel" {
  instance = google_compute_instance.agent_vm.name
  zone     = var.zone
  role     = "roles/iap.tunnelResourceAccessor"
  member   = "serviceAccount:${var.api_service_account_email}"
}

# Allow the FastAPI service account to read and write instance metadata
resource "google_project_iam_member" "api_compute_admin" {
  project = var.project_id
  role    = "roles/compute.instanceAdmin.v1"
  member  = "serviceAccount:${var.api_service_account_email}"
}
