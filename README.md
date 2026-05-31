# safe-god-mode

A FastAPI orchestrator that forwards a prompt to **Claude Code** running inside a
container on a GCP VM. Claude Code runs in `--dangerously-skip-permissions` ("god")
mode; the container + VM are the isolation boundary.

> **Status:** smoke-test stage. No auth in front of `/execute` yet — bind to
> `127.0.0.1` only until OIDC/SSO is added.

## Layout

```
safe-god-mode/
├── Dockerfile          # node:20-slim + python + claude-code, runs as non-root `agent`
├── requirements.txt
├── .dockerignore
├── .env.example        # copy to .env, add ANTHROPIC_API_KEY
└── src/
    └── main.py         # app = src.main:app
```

## Endpoints

| Method | Path        | Body                  | Returns                          |
|--------|-------------|-----------------------|----------------------------------|
| GET    | `/health`   | —                     | `{"status":"ok"}`                |
| POST   | `/execute`  | `{"prompt": "..."}`   | `{"code", "stdout", "stderr"}`   |

`/execute` shells out to `claude -p <prompt> --dangerously-skip-permissions`.

## Run

```bash
cp .env.example .env          # add your ANTHROPIC_API_KEY
docker build -t safe-god-mode .
docker run --rm -p 127.0.0.1:8000:8000 --env-file .env safe-god-mode
```

Test:

```bash
curl localhost:8000/health
curl -s localhost:8000/execute \
  -H 'content-type: application/json' \
  -d '{"prompt":"create hello.py that prints hi, then run it"}'
```

## Security notes

- **Bind to `127.0.0.1`** — the VM has a public IP and HTTP firewall is On.
  `0.0.0.0` on the host = public root-RCE. Keep it local until SSO is in front.
- **Never bake the API key into the image** — pass via `--env-file`/`-e`; `.env` is gitignored.
- **Set a hard spend cap** in the Anthropic Console — it bounds worst-case cost.
- **GCP metadata (`169.254.169.254`)** still hands out the VM's service-account token
  (currently Storage read-only). Strip/replace the default SA before real use.

## Next steps

- [ ] OIDC/SSO (Auth0) in front of `/execute`
- [ ] `/ws/terminal` websocket for live stdout streaming
- [ ] Telegram webhook trigger (with secret-token verification + sender allowlist)
- [ ] Lock down GCP service account + metadata access
