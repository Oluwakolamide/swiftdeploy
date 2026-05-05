# SwiftDeploy

> **HNG Internship — DevOps Track — Stage 4A + 4B**
>
> A declarative container deployment CLI that generates all infrastructure configs from a single `manifest.yaml`, enforces deployment policies via OPA, exposes Prometheus metrics, and provides a live observability dashboard.

---

## How it works

```
manifest.yaml ──► swiftdeploy init ──► nginx.conf
                                   └──► docker-compose.yml
                                               │
                              docker compose up▼
          ┌────────────┐    ┌──────────────┐    ┌─────────────┐
          │   nginx    │◄───│  API service │    │     OPA     │
          │   :8080    │    │   :3000      │    │  :8181      │
          └────────────┘    └──────────────┘    └─────────────┘
               ▲                  │                    ▲
               │            /metrics                   │
               │          Prometheus              policy queries
               └──────── swiftdeploy CLI ──────────────┘
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
git clone https://github.com/Oluwakolamide/swiftdeploy.git
cd swiftdeploy

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install CLI dependency
pip install pyyaml

# 4. Build the service image
docker build -t swift-deploy-1-node:latest .

# 5. Deploy (runs OPA policy check first)
python3 swiftdeploy deploy
```

---

## manifest.yaml — the source of truth

```yaml
services:
  image: swift-deploy-1-node:latest
  port: 3000
  mode: stable          # stable | canary
  version: "1.0.0"
  restart_policy: unless-stopped

nginx:
  image: nginx:latest
  port: 8080
  proxy_timeout: 30

network:
  name: swiftdeploy-net
  driver_type: bridge

volumes:
  logs: swiftdeploy-logs
```

You may extend these fields but **must not remove** the base required fields.

---

## Subcommand walkthrough

### `python3 swiftdeploy init`

Parses `manifest.yaml` and generates configs from templates:

- `nginx.conf` — from `templates/nginx.conf.tmpl`
- `docker-compose.yml` — from `templates/docker-compose.yml.tmpl`

```
▶  swiftdeploy init
  ✔  Generated  nginx.conf  (nginx:8080 → service:3000)
  ✔  Generated  docker-compose.yml  (mode=stable)
  ✔  policies/ directory found (4 files)

  Init complete.
```

---

### `python3 swiftdeploy validate`

Runs 5 pre-flight checks. Exits non-zero if any fail.

```
▶  swiftdeploy validate — 5 pre-flight checks
  ✔  [PASS]  manifest.yaml exists and is valid YAML
  ✔  [PASS]  All required fields are present and non-empty
  ✔  [PASS]  Docker image referenced in manifest exists locally
  ✔  [PASS]  Nginx port is not already bound on the host
  ✔  [PASS]  Generated nginx.conf is syntactically valid

  Result: 5/5 checks passed.
```

---

### `python3 swiftdeploy deploy`

Starts OPA first, runs pre-deploy policy check, then brings up the full stack.

```
▶  swiftdeploy deploy
▶  swiftdeploy init
  ✔  Generated nginx.conf
  ✔  Generated docker-compose.yml
  ✔  policies/ directory found (4 files)

▶  Starting OPA …
  ✔  OPA is ready.

▶  OPA pre-deploy policy check
  disk_free=183.76 GB  cpu_load=1.45
  ✔  [PASS]  infrastructure: PASS — All infrastructure checks passed

▶  Bringing up stack …
  ✔  Container swiftdeploy-service  Healthy
  ✔  Container swiftdeploy-nginx    Started
  ✔  Container swiftdeploy-opa      Started

  ✔  Health check passed!  uptime=5.3s
  Stack deployed successfully.
```

If policy fails, deploy is blocked:

```
  ✘  [BLOCK]  infrastructure: BLOCKED — CPU load 5.66 exceeds maximum 2.00
  ✘  Deploy BLOCKED by policy. Resolve violations and retry.
```

---

### `python3 swiftdeploy promote [canary|stable]`

Switches deployment mode with a rolling service-only restart. Promotion to `stable` triggers an OPA canary safety check first.

```bash
python3 swiftdeploy promote canary
python3 swiftdeploy promote stable   # triggers pre-promote OPA check
```

```
▶  swiftdeploy promote → stable
▶  OPA pre-promote policy check — measuring canary health (10 s) …
  error_rate=0.0%  p99=12ms
  ✔  [PASS]  canary: PASS — Canary health checks passed

  ✔  manifest.yaml updated: mode = canary → stable
  ✔  docker-compose.yml regenerated.
  ✔  Mode confirmed: stable  uptime=2.1s
  Promotion to 'stable' complete.
```

---

### `python3 swiftdeploy status`

Live-refreshing terminal dashboard. Scrapes `/metrics`, calculates real-time req/s and P99 latency, and queries OPA for policy compliance. Appends every scrape to `history.jsonl`.

```
             SwiftDeploy Status Dashboard
──────────────────────────────────────────────────────────────
  Mode: canary     Chaos: none

  Performance───────────────────────────────────────────────
  Req/s         1.39 req/s
  P99 Latency   12 ms
  Error Rate    0.000 %

  Policy Compliance─────────────────────────────────────────
  ✔ [PASS] infrastructure: PASS — All infrastructure checks passed
  ✔ [PASS] canary: PASS — Canary health checks passed

  Updated: 2026-05-05T20:17:59Z   Refresh: 5s
  History: history.jsonl
──────────────────────────────────────────────────────────────
```

Press **Ctrl+C** to stop.

---

### `python3 swiftdeploy audit`

Parses `history.jsonl` and generates `audit_report.md` — a GitHub Flavored Markdown report with timeline, mode changes, chaos events, and policy violations.

```
▶  swiftdeploy audit
  ✔  Loaded 42 records from history.jsonl
  ✔  Report written to audit_report.md
```

---

### `python3 swiftdeploy teardown [--clean]`

Stops and removes all containers, networks, and volumes.

```bash
python3 swiftdeploy teardown           # keep generated configs
python3 swiftdeploy teardown --clean   # also delete nginx.conf + docker-compose.yml
```

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Welcome message with mode, version, timestamp |
| `GET` | `/healthz` | `{"status":"ok","uptime":<seconds>}` |
| `GET` | `/metrics` | Prometheus text format metrics |
| `POST` | `/chaos` | Inject failure behaviour (**canary mode only**) |

### Prometheus metrics exposed

| Metric | Type | Description |
|--------|------|-------------|
| `http_requests_total` | Counter | Total requests (labels: method, path, status_code) |
| `http_request_duration_seconds` | Histogram | Request latency with standard buckets |
| `app_uptime_seconds` | Gauge | Seconds since process start |
| `app_mode` | Gauge | 0=stable, 1=canary |
| `chaos_active` | Gauge | 0=none, 1=slow, 2=error |

### Chaos modes (canary only)

```bash
# Slow responses
curl -X POST http://localhost:8080/chaos \
  -H 'Content-Type: application/json' \
  -d '{"mode":"slow","duration":3}'

# Random 500 errors at 50% rate
curl -X POST http://localhost:8080/chaos \
  -H 'Content-Type: application/json' \
  -d '{"mode":"error","rate":0.5}'

# Recover
curl -X POST http://localhost:8080/chaos \
  -H 'Content-Type: application/json' \
  -d '{"mode":"recover"}'
```

---

## OPA Policy Architecture

OPA runs as a sidecar container, reachable by the CLI at `127.0.0.1:8181` but **never accessible through nginx**. All decision logic lives exclusively in OPA — the CLI never makes allow/deny decisions itself.

### Infrastructure policy (pre-deploy)

Defined in `policies/infrastructure.rego`. Blocks deployment if:
- Disk free < 10 GB
- CPU load > threshold

### Canary safety policy (pre-promote)

Defined in `policies/canary.rego`. Blocks promotion to stable if:
- Error rate > 1%
- P99 latency > 500ms

### Threshold configuration

All threshold values live in `policies/data.json` — never hardcoded in Rego files:

```json
{
  "thresholds": {
    "min_disk_free_gb":   10.0,
    "max_cpu_load":        2.0,
    "max_error_rate_pct":  1.0,
    "max_p99_latency_ms": 500.0
  }
}
```

---

## Nginx features

- Listens on `nginx.port` (default 8080)
- Timeouts driven by `nginx.proxy_timeout`
- JSON error bodies on 502/503/504
- `X-Deployed-By: swiftdeploy` header on every response
- Forwards `X-Mode` header from upstream (canary signal)
- Access log: `$time_iso8601 | $status | ${request_time}s | $upstream_addr | $request`

---

## Security hardening

- Service container runs as UID/GID 1001 (`appuser`)
- All Linux capabilities dropped (`cap_drop: ALL`)
- `no-new-privileges:true` security option
- Service port **never** exposed to host — all traffic routes through Nginx
- OPA port bound to `127.0.0.1` only — not reachable externally
- Multi-stage Docker build keeps image under 300 MB

---

## Project structure

```
.
├── manifest.yaml                   # ← single source of truth (only file you edit)
├── swiftdeploy                     # ← CLI executable
├── Dockerfile                      # ← builds swift-deploy-1-node:latest
├── app/
│   ├── main.py                     # Flask + Gunicorn + Prometheus metrics
│   └── requirements.txt
├── templates/
│   ├── nginx.conf.tmpl             # Nginx config template
│   └── docker-compose.yml.tmpl    # Compose template (includes OPA)
└── policies/
    ├── infrastructure.rego         # pre-deploy policy domain
    ├── canary.rego                 # pre-promote policy domain
    └── data.json                   # threshold values (not in Rego)
```

Generated by `swiftdeploy init` (gitignored):

```
├── nginx.conf
└── docker-compose.yml
```

Generated at runtime (gitignored):

```
├── history.jsonl
└── audit_report.md
```
