package swiftdeploy.canary

import rego.v1

# ── Decision ────────────────────────────────────────────────────────────────
# Independently answers: "Is this canary safe to promote to stable?"
# A change here never requires touching infrastructure.rego.

default allow := false

allow if {
    error_rate_ok
    latency_ok
}

# ── Sub-rules ────────────────────────────────────────────────────────────────
error_rate_ok if input.error_rate_pct <= data.thresholds.max_error_rate_pct
latency_ok    if input.p99_latency_ms <= data.thresholds.max_p99_latency_ms

# ── Reasoning ────────────────────────────────────────────────────────────────
reason := msg if {
    not error_rate_ok
    msg := sprintf(
        "BLOCKED — Error rate %.2f%% exceeds maximum %.2f%%",
        [input.error_rate_pct, data.thresholds.max_error_rate_pct],
    )
} else := msg if {
    not latency_ok
    msg := sprintf(
        "BLOCKED — P99 latency %.0fms exceeds maximum %.0fms",
        [input.p99_latency_ms, data.thresholds.max_p99_latency_ms],
    )
} else := "PASS — Canary health checks passed"

# ── Structured output ────────────────────────────────────────────────────────
decision := {
    "allow":  allow,
    "reason": reason,
    "input":  input,
    "domain": "canary",
}
