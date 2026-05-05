# SwiftDeploy

> **HNG Internship — DevOps Track — Stage 4A**
>
> A declarative container deployment CLI that generates all infrastructure configs from a single `manifest.yaml` and manages the full container lifecycle.

---

## How it works

```
manifest.yaml  ──► swiftdeploy init ──► nginx.conf
                                    └──► docker-compose.yml
                                              │
                             docker compose up▼
                         ┌────────────┐    ┌──────────────┐
                         │  nginx     │◄───│  API service │
                         │  :8080     │    │  :3000       │
                         └────────────┘    └──────────────┘
```

`manifest.yaml` is the **single source of truth**. The grader deletes generated files and re-runs `swiftdeploy init` to verify they regenerate correctly. Nothing is hand-written.

---

## Prerequisites

| Tool | Min version |
|------|-------------|
| Docker | 24+ (with Docker Compose V2 plugin) |
| Python | 3.10+ |
| PyYAML | `pip install pyyaml` |

---

## Quick setup

```bash
# 1. Clone the repo
git clone https://github.com/<your-handle>/swiftdeploy.git
cd swiftdeploy

# 2. Install CLI dependency
pip install pyyaml

# 3. Build the service image (must match manifest.yaml services.image)
docker build -t swift-deploy-1-node:latest .

# 4. Deploy
./swiftdeploy deploy
```

---

## manifest.yaml — the source of truth

```yaml
services:
  image: swift-deploy-1-node:latest   # Docker image (must exist locally)
  port: 3000                          # Container-internal port
  mode: stable                        # stable | canary
  version: "1.0.0"
  restart_policy: unless-stopped

nginx:
  image: nginx:latest
  port: 8080                          # Host-exposed port
  proxy_timeout: 30                   # connect / send / read timeout (seconds)

network:
  name: swiftdeploy-net
  driver_type: bridge

volumes:
  logs: swiftdeploy-logs
```

You may extend these fields but **must not remove** the base required fields.

---

## Subcommand walkthrough

### `./swiftdeploy init`

Parses `manifest.yaml` and generates two files from templates:

- `nginx.conf` — from `templates/nginx.conf.tmpl`
- `docker-compose.yml` — from `templates/docker-compose.yml.tmpl`

```bash
./swiftdeploy init
```

```
▶  swiftdeploy init
  ✔  Generated  nginx.conf  (nginx port 8080 → service port 3000)
  ✔  Generated  docker-compose.yml  (mode=stable, version=1.0.0)

  Init complete. Edit manifest.yaml and re-run to regenerate.
```

---

### `./swiftdeploy validate`

Runs 5 pre-flight checks. Exits non-zero if any fail.

```bash
./swiftdeploy validate
```

```
▶  swiftdeploy validate — 5 pre-flight checks

  ✔  [PASS]  manifest.yaml exists and is valid YAML
  ✔  [PASS]  All required fields are present and non-empty
  ✔  [PASS]  Docker image referenced in manifest exists locally
  ✔  [PASS]  Nginx port is not already bound on the host
  ✔  [PASS]  Generated nginx.conf is syntactically valid

  Result: 5/5 checks passed.
```

| Check | What it tests |
|-------|--------------|
| 1 | `manifest.yaml` exists and parses as valid YAML |
| 2 | All 6 required fields present and non-empty |
| 3 | `docker image inspect <image>` succeeds |
| 4 | TCP connect to nginx port returns refused (port free) |
| 5 | `nginx -t` via Docker container succeeds |

---

### `./swiftdeploy deploy`

Runs `init`, brings up the stack, and blocks until `/healthz` returns `200` or 60 seconds elapse.

```bash
./swiftdeploy deploy
```

```
▶  swiftdeploy deploy
▶  swiftdeploy init
  ✔  Generated  nginx.conf
  ✔  Generated  docker-compose.yml

▶  Bringing up stack …
[+] Running 3/3
 ✔ Network swiftdeploy-net  Created
 ✔ Container swiftdeploy-service  Started
 ✔ Container swiftdeploy-nginx  Started

  Waiting for service at http://localhost:8080/healthz …
......
  ✔  Health check passed!  uptime=4.2s

  Stack deployed successfully.
```

---

### `./swiftdeploy promote [canary|stable]`

Switches deployment mode with a rolling service-only restart.

```bash
./swiftdeploy promote canary
```

What happens:
1. Updates `mode:` field in `manifest.yaml` in-place
2. Regenerates `docker-compose.yml` with the new `MODE` env var
3. Restarts **only** the service container (`--no-deps --force-recreate`)
4. Hits `/healthz` to confirm `X-Mode: canary` header is present

```
▶  swiftdeploy promote → canary
  ✔  manifest.yaml updated:  mode = stable → canary
  ✔  docker-compose.yml regenerated with new MODE env var.

▶  Restarting service container …

  Verifying mode switch at http://localhost:8080/healthz …
...
  ✔  Mode confirmed: canary  (X-Mode: canary ✔)  uptime=1.7s

  Promotion to 'canary' complete.
```

Reverse with `./swiftdeploy promote stable`.

---

### `./swiftdeploy teardown [--clean]`

Stops and removes all containers, networks, and volumes.

```bash
./swiftdeploy teardown           # remove stack, keep generated configs
./swiftdeploy teardown --clean   # also delete nginx.conf + docker-compose.yml
```

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Welcome message with mode, version, timestamp |
| `GET` | `/healthz` | Liveness check: `{"status":"ok","uptime":<seconds>}` |
| `POST` | `/chaos` | Inject failure behaviour (**canary mode only**) |

### Chaos modes (canary only)

```bash
# Simulate slow responses (sleep N seconds)
curl -X POST http://localhost:8080/chaos \
  -H 'Content-Type: application/json' \
  -d '{"mode":"slow","duration":3}'

# Random 500 errors at 50% rate
curl -X POST http://localhost:8080/chaos \
  -H 'Content-Type: application/json' \
  -d '{"mode":"error","rate":0.5}'

# Recover — cancel all active chaos
curl -X POST http://localhost:8080/chaos \
  -H 'Content-Type: application/json' \
  -d '{"mode":"recover"}'
```

---

## Nginx features

- Listens on `nginx.port` (default 8080)
- Timeouts from `nginx.proxy_timeout`
- JSON error bodies on 502/503/504
- `X-Deployed-By: swiftdeploy` header on every response
- Forwards `X-Mode` header from upstream to client
- Access log format: `$time_iso8601 | $status | ${request_time}s | $upstream_addr | $request`

---

## Security hardening

- Service container runs as UID/GID 1001 (`appuser`)
- All Linux capabilities dropped (`cap_drop: ALL`)
- `no-new-privileges:true` security option
- Service port **never** exposed to host — all traffic routes through Nginx
- Multi-stage Docker build keeps image under 300 MB
- `PYTHONUNBUFFERED` and `PYTHONDONTWRITEBYTECODE` set

---

## Project structure

```
.
├── manifest.yaml              # ← single source of truth (edit this)
├── swiftdeploy                # ← CLI executable
├── Dockerfile                 # ← builds swift-deploy-1-node:latest
├── .dockerignore
├── app/
│   ├── main.py                # Python API service (Flask + Gunicorn)
│   └── requirements.txt
├── templates/
│   ├── nginx.conf.tmpl        # Nginx config template
│   └── docker-compose.yml.tmpl
└── README.md
```

Generated (by `swiftdeploy init`, gitignored):

```
├── nginx.conf
└── docker-compose.yml
```

---

## .gitignore recommendation

```
nginx.conf
docker-compose.yml
__pycache__/
*.pyc
```
