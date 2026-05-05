package swiftdeploy.infrastructure

import rego.v1

# ── Decision ────────────────────────────────────────────────────────────────
# Every decision carries an explicit reason — never a bare boolean.

default allow := false

allow if {
    disk_ok
    cpu_ok
}

# ── Sub-rules ────────────────────────────────────────────────────────────────
disk_ok if input.disk_free_gb >= data.thresholds.min_disk_free_gb
cpu_ok  if input.cpu_load     <= data.thresholds.max_cpu_load

# ── Reasoning ────────────────────────────────────────────────────────────────
reason := msg if {
    not disk_ok
    msg := sprintf(
        "BLOCKED — Disk free %.1f GB is below minimum %.1f GB",
        [input.disk_free_gb, data.thresholds.min_disk_free_gb],
    )
} else := msg if {
    not cpu_ok
    msg := sprintf(
        "BLOCKED — CPU load %.2f exceeds maximum %.2f",
        [input.cpu_load, data.thresholds.max_cpu_load],
    )
} else := "PASS — All infrastructure checks passed"

# ── Structured output (CLI reads this object) ─────────────────────────────────
decision := {
    "allow":  allow,
    "reason": reason,
    "input":  input,
    "domain": "infrastructure",
}
