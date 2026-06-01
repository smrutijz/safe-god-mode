# Terraform Setup Guide

This folder contains the infrastructure-as-code to provision the entire GCP
architecture — VPC, firewall rules, NAT, and the private VM that runs Claude.

---

## What Terraform does here

Running `terraform apply` creates all of this automatically on GCP:

```
✅ Custom VPC (prod-secure-vpc)
✅ Private subnet (10.0.1.0/24) — no public IPs
✅ Cloud Router + Cloud NAT — VM can reach internet outbound only
✅ Ingress firewall — SSH allowed only from Google IAP (35.235.240.0/20)
✅ Egress firewall — deny all by default
✅ Egress exceptions — PostgreSQL (port 5432) + HTTPS (port 443)
✅ e2-micro VM on Debian 12 — no public IP, metadata SSH keys enabled
✅ IAM bindings — FastAPI service account gets IAP + metadata write access
```

---

## Prerequisites (do these once before anything else)

### 1. Install Terraform

**Windows:**
```
winget install HashiCorp.Terraform
```
Verify: `terraform -version`

### 2. Install gcloud CLI (if not already installed)

Download from: https://cloud.google.com/sdk/docs/install

Then authenticate:
```bash
gcloud auth login
gcloud auth application-default login
```

### 3. Create a GCP project

If you don't have one:
```bash
gcloud projects create YOUR-PROJECT-ID
gcloud config set project YOUR-PROJECT-ID
```

Enable the required APIs:
```bash
gcloud services enable compute.googleapis.com
gcloud services enable iap.googleapis.com
```

### 4. Create two service accounts

**Service account for the VM** (what the VM runs as):
```bash
gcloud iam service-accounts create vm-sa \
  --display-name="Secure Agent VM"
```

**Service account for the FastAPI server** (what the API uses to open tunnels):
```bash
gcloud iam service-accounts create api-sa \
  --display-name="FastAPI IAP Tunnel Access"
```

Get their emails (you will need these in tfvars):
```bash
gcloud iam service-accounts list
# Looks like: vm-sa@YOUR-PROJECT-ID.iam.gserviceaccount.com
```

---

## Setup

### Step 1 — Copy and fill in your values

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` — fill in every value:

| Variable | Where to find it |
|---|---|
| `project_id` | Your GCP project ID |
| `region` | e.g. `asia-southeast1` |
| `zone` | e.g. `asia-southeast1-a` |
| `machine_type` | Keep `e2-micro` for budget |
| `postgres_db_cidr` | Your DB IP with `/32` e.g. `1.2.3.4/32` |
| `vm_service_account_email` | `vm-sa@YOUR-PROJECT.iam.gserviceaccount.com` |
| `api_service_account_email` | `api-sa@YOUR-PROJECT.iam.gserviceaccount.com` |

> `terraform.tfvars` is gitignored — it contains real IPs and account names.

### Step 2 — Initialise (download GCP plugin)

```bash
terraform init
```

Only needed once, or after adding new providers.

### Step 3 — Preview what will be built

```bash
terraform plan
```

Shows every resource Terraform will create. **Nothing is built yet.**
Read through it and confirm it matches what you expect.

### Step 4 — Build the infrastructure

```bash
terraform apply
```

Type `yes` when prompted. Takes about 2-3 minutes.

When done it prints:

```
Outputs:
project_id = "your-project-id"   ← GCP_PROJECT in .env
vm_name    = "secure-agent-vm"   ← VM_NAME in .env
zone       = "asia-southeast1-a" ← GCP_ZONE in .env
```

Copy these values straight into your FastAPI `.env` file.

---

## After Terraform — install Claude on the VM

Once the VM exists, SSH in via IAP and install Claude:

```bash
# SSH in (no public IP needed — IAP handles it)
gcloud compute ssh secure-agent-vm --zone=asia-southeast1-a --tunnel-through-iap

# Inside the VM — install Node + Claude Code
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo bash -
sudo apt-get install -y nodejs
sudo npm install -g @anthropic-ai/claude-code

# Log in to Claude (do this once interactively)
claude

# Exit the VM
exit

# Copy your Claude credentials from local machine to VM
gcloud compute scp --recurse ~/.claude secure-agent-vm:~/.claude \
  --zone=asia-southeast1-a --tunnel-through-iap
gcloud compute scp ~/.claude.json secure-agent-vm:~/.claude.json \
  --zone=asia-southeast1-a --tunnel-through-iap
```

---

## Tearing it all down

```bash
terraform destroy
```

Deletes everything Terraform created. Type `yes` to confirm.

> This will also delete the VM and all its data. The VPC, firewall rules, NAT
> are all removed. Your FastAPI code and repo are unaffected.

---

## Important note — OS Login is disabled

The VM has `enable-oslogin = "FALSE"`. This is intentional.

The FastAPI server injects ephemeral SSH keys via GCP instance metadata.
OS Login and metadata-based SSH keys are mutually exclusive — if OS Login
were enabled, GCP would silently ignore all metadata SSH keys and the
FastAPI connection would always fail.

---

## Files

| File | Purpose |
|---|---|
| `main.tf` | All infrastructure resources |
| `variables.tf` | Input variable declarations |
| `outputs.tf` | Values printed after apply |
| `terraform.tfvars.example` | Template — copy to `terraform.tfvars` |
| `terraform.tfvars` | Your real values — **gitignored, never commit** |
