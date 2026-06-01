# safe-god-mode

A FastAPI orchestrator that forwards prompts to **Claude Code** running on a
separate private GCP VM. The API server has **no Claude installed** — it reaches
the VM securely through a **GCP IAP tunnel + asyncssh** connection using
per-request ephemeral SSH keys.

> **Status:** smoke-test stage. No auth in front of endpoints yet — bind to
> `127.0.0.1` only until OIDC/SSO is added.

## Architecture

```
[Client]
   │
   ▼  HTTP / WebSocket
[API Server]  ──── gcloud IAP tunnel ────►  [Private VM]
 FastAPI            ephemeral ED25519         claude CLI + shell
 asyncssh           key per request           no public IP
 no Claude          injected via GCP API
```

Every request:
1. Generate a throwaway ED25519 key pair in memory
2. Inject the public key into VM instance metadata (5-min GCP expiry)
3. Open `gcloud compute start-iap-tunnel` in parallel with key injection
4. Connect via asyncssh through the tunnel using the ephemeral private key
5. Run the command / open the shell; stream output back
6. On exit: remove key from metadata, close tunnel

## Layout

```
safe-god-mode/
├── Dockerfile            # API server image: Python + gcloud CLI (no Claude)
├── docker-compose.yml    # runs the API container; mounts gcloud creds
├── requirements.txt
├── .env.example
└── src/
    ├── main.py
    ├── core/
    │   ├── config.py     # settings (GCP project/zone/VM, timeouts)
    │   └── iap.py        # ephemeral key lifecycle + IAP tunnel + SSH connection
    └── api/v1/
        ├── execute.py    # POST /api/v1/execute    (sync, full output)
        ├── jobs.py       # POST/GET /api/v1/jobs   (async, background)
        ├── stream.py     # WS /api/v1/ws/jobs/{id} (line-by-line stream)
        └── terminal.py   # WS /api/v1/ws/terminal  (interactive PTY shell)
```

## Prerequisites

### API server
- Python 3.12+
- `gcloud` CLI installed and authenticated (see step 2 below)
- GCP account with IAP tunnel + Compute instance metadata permissions

### VM
- Claude Code CLI installed (`npm install -g @anthropic-ai/claude-code`)
- Claude credentials in place (`~/.claude` and `~/.claude.json`)
- SSH server running on port 22
- GCP IAP firewall rule: allow port 22 from `35.235.240.0/20` (standard GCP default)

## Setup

### 1. Install Claude on the VM

```bash
# SSH in initially via IAP
gcloud compute ssh VM_NAME --zone=ZONE --project=PROJECT

# install Node + Claude Code
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo bash -
sudo apt-get install -y nodejs
sudo npm install -g @anthropic-ai/claude-code

# log in interactively once to populate ~/.claude
claude

# verify
claude --version
```

### 2. Copy Claude credentials to the VM

```bash
gcloud compute scp --recurse ~/.claude VM_NAME:~/.claude --zone=ZONE --project=PROJECT
gcloud compute scp ~/.claude.json VM_NAME:~/.claude.json --zone=ZONE --project=PROJECT
```

Credentials stay valid as long as you don't log out of claude.ai.

### 3. Authenticate gcloud on the API server

```bash
# option A — user account (local/dev)
gcloud auth login
gcloud auth application-default login
gcloud config set project PROJECT

# option B — service account (production)
gcloud auth activate-service-account --key-file=sa-key.json
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa-key.json
```

### 4. Grant required IAM roles

The API server's account needs two permissions:

```bash
# 1. Open IAP tunnels
gcloud projects add-iam-policy-binding PROJECT \
  --member="user:you@example.com" \
  --role="roles/iap.tunnelResourceAccessor"

# 2. Read and write instance metadata (for ephemeral SSH key injection)
gcloud projects add-iam-policy-binding PROJECT \
  --member="user:you@example.com" \
  --role="roles/compute.instanceAdmin.v1"
```

> `compute.instanceAdmin.v1` is broad — for production, create a custom role with
> only `compute.instances.get` and `compute.instances.setMetadata`.

### 5. Configure and run

```bash
cp .env.example .env
# fill in GCP_PROJECT, GCP_ZONE, VM_NAME, VM_USER

pip install -r requirements.txt
uvicorn src.main:app --host 127.0.0.1 --port 8000
```

**With Docker:**
```bash
docker compose up -d
```

## Endpoints

| Method    | Path                    | Body / Input                    | Returns / Output                  |
|-----------|-------------------------|---------------------------------|-----------------------------------|
| GET       | `/health`               | —                               | `{"status":"ok"}`                 |
| POST      | `/api/v1/execute`       | `{"prompt":"...","timeout"?:N}` | `{"code","stdout","stderr"}`      |
| POST      | `/api/v1/jobs`          | `{"prompt":"..."}`              | `{"job_id","status"}`             |
| GET       | `/api/v1/jobs/{id}`     | —                               | `{"job_id","status","output"}`    |
| WebSocket | `/api/v1/ws/jobs/{id}`  | —                               | live line-by-line claude output   |
| WebSocket | `/api/v1/ws/terminal`   | `{"type":"data","data":"..."}` `{"type":"resize","cols":N,"rows":N}` | `{"type":"data"/"exit"/"error"}` |

### Terminal WebSocket protocol

**Client → Server:**
```json
{"type": "data",   "data": "ls -la\n"}
{"type": "resize", "cols": 120, "rows": 40}
```

**Server → Client:**
```json
{"type": "data",  "data": "<terminal output>"}
{"type": "exit",  "code": 0}
{"type": "error", "detail": "SSH auth failed ..."}
```

## Configuration

| Variable       | Default   | Description                                      |
|----------------|-----------|--------------------------------------------------|
| `GCP_PROJECT`  | —         | GCP project ID (**required**)                    |
| `GCP_ZONE`     | —         | VM zone e.g. `asia-southeast1-a` (**required**)  |
| `VM_NAME`      | —         | VM instance name (**required**)                  |
| `VM_USER`      | —         | Linux user on the VM (**required**)              |
| `CLAUDE_BIN`   | `claude`  | Path to claude CLI on the VM                     |
| `SYNC_TIMEOUT` | `120`     | Max seconds `/execute` waits before 504          |

## Test

```bash
curl localhost:8000/health

curl -s localhost:8000/api/v1/execute \
  -H 'content-type: application/json' \
  -d '{"prompt":"create hello.py that prints hi, then run it"}'
```

## Security notes

- **Ephemeral keys** — no static SSH key on disk. A fresh ED25519 key is generated per request, injected with a 5-min GCP expiry, and removed immediately on exit. A stolen key is useless within seconds.
- **VM has no public IP** — the only ingress path is IAP (`35.235.240.0/20` → port 22).
- **API binds to `127.0.0.1`** — put a reverse proxy + SSO in front before exposing publicly.
- **Claude credentials never in the image** — mounted at runtime on the VM only.
- **One tunnel per request** — the IAP tunnel opens and closes each call. A persistent connection pool can reduce latency later.
- **Set a hard spend cap** in the Anthropic Console if using API key auth.
- **Tighten the IAM role** — replace `compute.instanceAdmin.v1` with a custom role scoped to `get` + `setMetadata` only.

## Next steps

- [ ] OIDC/SSO (Auth0) in front of the API
- [ ] Persistent SSH connection pool (removes per-request tunnel overhead)
- [ ] Custom IAM role (scope down from instanceAdmin to get + setMetadata only)
- [ ] Lock down GCP service account + metadata access
