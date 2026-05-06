package swiftdeploy.canary_safety

observed := object.get(input, "observed", {})
current_mode := object.get(observed, "current_mode", "stable")
error_rate_pct := object.get(observed, "error_rate_pct", -1)
p99_latency_ms := object.get(observed, "p99_latency_ms", -1)

violation[msg] if {
    current_mode == "canary"
    error_rate_pct < 0
    msg := "error_rate_pct metric is missing from input"
}

violation[msg] if {
    current_mode == "canary"
    p99_latency_ms < 0
    msg := "p99_latency_ms metric is missing from input"
}

violation[msg] if {
    current_mode == "canary"
    error_rate_pct >= 0
    error_rate_pct > data.config.canary_safety.max_error_rate_pct
    msg := sprintf("Error rate %.3f%% exceeds max %.3f%%", [error_rate_pct, data.config.canary_safety.max_error_rate_pct])
}

violation[msg] if {
    current_mode == "canary"
    p99_latency_ms >= 0
    p99_latency_ms > data.config.canary_safety.max_p99_latency_ms
    msg := sprintf("P99 latency %.2fms exceeds max %.2fms", [p99_latency_ms, data.config.canary_safety.max_p99_latency_ms])
}

decision := {
    "allow": true,
    "domain": "canary_safety",
    "reasons": ["Canary safety check skipped because current mode is not canary"],
    "violations": [],
    "observed": {
        "current_mode": current_mode,
        "error_rate_pct": error_rate_pct,
        "p99_latency_ms": p99_latency_ms,
    },
} if {
    current_mode != "canary"
}

decision := {
    "allow": allow,
    "domain": "canary_safety",
    "reasons": reasons,
    "violations": vs,
    "observed": {
        "current_mode": current_mode,
        "error_rate_pct": error_rate_pct,
        "p99_latency_ms": p99_latency_ms,
    },
} if {
    current_mode == "canary"
    vs := [v | v := violation[_]]
    allow := count(vs) == 0
    reasons := ["Canary safety checks passed"]
    allow
}

decision := {
    "allow": false,
    "domain": "canary_safety",
    "reasons": reasons,
    "violations": vs,
    "observed": {
        "current_mode": current_mode,
        "error_rate_pct": error_rate_pct,
        "p99_latency_ms": p99_latency_ms,
    },
} if {
    current_mode == "canary"
    vs := [v | v := violation[_]]
    count(vs) > 0
    reasons := [r | r := vs[_]]
}
