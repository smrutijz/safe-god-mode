# safe-god-mode

A FastAPI orchestrator that forwards a prompt to **Claude Code** running inside a
container on a GCP VM. Claude Code runs in `--dangerously-skip-permissions` ("god")
mode; the container + VM are the isolation boundary.

> **Status:** smoke-test stage. No auth in front of `/execute` yet — bind to
> `127.0.0.1` only until OIDC/SSO is added.

## Layout

```
safe-god-mode/
├── Dockerfile            # node:20-slim + python + claude-code, runs as non-root `agent`
├── docker-compose.yml    # mounts ~/.claude for auth, binds to 127.0.0.1:8000
├── requirements.txt
├── .dockerignore
├── .env.example          # only needed if using ANTHROPIC_API_KEY instead of .claude mount
└── src/
    ├── main.py           # app = src.main:app, wires all routers
    └── api/v1/
        ├── execute.py    # POST /api/v1/execute  (sync)
        ├── jobs.py       # POST/GET /api/v1/jobs (async)
        └── stream.py     # WS /api/v1/ws/jobs/{id} (streaming)
```

## Endpoints

| Method    | Path                      | Body                | Returns                          |
|-----------|---------------------------|---------------------|----------------------------------|
| GET       | `/health`                 | —                   | `{"status":"ok"}`                |
| POST      | `/api/v1/execute`         | `{"prompt": "..."}` | `{"code", "stdout", "stderr"}`   |
| POST      | `/api/v1/jobs`            | `{"prompt": "..."}` | `{"job_id", "status"}`           |
| GET       | `/api/v1/jobs/{id}`       | —                   | `{"job_id", "status", "output"}` |
| WebSocket | `/api/v1/ws/jobs/{id}`    | —                   | live line-by-line stream         |

## VM setup (one-time)

```bash
# 1. from your local machine — copy Claude credentials to the VM
scp -r ~/.claude smrut@VM_IP:~/.claude
scp ~/.claude.json smrut@VM_IP:~/.claude.json

# 2. SSH into the VM
ssh smrut@VM_IP

# 3. clone the repo
git clone https://github.com/smrutijz/safe-god-mode.git
cd safe-god-mode

# 4. start the service
docker compose up -d
```

The `docker-compose.yml` mounts `/home/smrut/.claude` read-only into the container.
As long as you don't log out of claude.ai, the refresh token stays alive indefinitely.

**Alternative — API key:** copy `.env` to the VM via `scp`, then run:
```bash
docker run --rm -p 127.0.0.1:8000:8000 --env-file .env safe-god-mode
```

Test:

```bash
curl localhost:8000/health
curl -s localhost:8000/api/v1/execute \
  -H 'content-type: application/json' \
  -d '{"prompt":"create hello.py that prints hi, then run it"}'
```

## Security notes

- **Bind to `127.0.0.1`** — the VM has a public IP and HTTP firewall is On.
  `0.0.0.0` on the host = public root-RCE. Keep it local until SSO is in front.
- **Never bake credentials into the image** — `.claude` is mounted at runtime; `.env` is gitignored.
- **Set a hard spend cap** in the Anthropic Console if switching to API key auth.
- **GCP metadata (`169.254.169.254`)** still hands out the VM's service-account token
  (currently Storage read-only). Strip/replace the default SA before real use.

## Next steps

- [ ] OIDC/SSO (Auth0) in front of `/execute`
- [ ] `/ws/terminal` websocket for live stdout streaming
- [ ] Telegram webhook trigger (with secret-token verification + sender allowlist)
- [ ] Lock down GCP service account + metadata access
