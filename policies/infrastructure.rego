package swiftdeploy.infrastructure

host := object.get(input, "host", {})
disk_free_gb := object.get(host, "disk_free_gb", -1)
cpu_load := object.get(host, "cpu_load", -1)

violation[msg] if {
    disk_free_gb < 0
    msg := "disk_free_gb metric is missing from input"
}

violation[msg] if {
    cpu_load < 0
    msg := "cpu_load metric is missing from input"
}

violation[msg] if {
    disk_free_gb >= 0
    disk_free_gb < data.config.infrastructure.min_disk_free_gb
    msg := sprintf("Disk free %.2fGB is below minimum %.2fGB", [disk_free_gb, data.config.infrastructure.min_disk_free_gb])
}

violation[msg] if {
    cpu_load >= 0
    cpu_load > data.config.infrastructure.max_cpu_load
    msg := sprintf("CPU load %.2f is above maximum %.2f", [cpu_load, data.config.infrastructure.max_cpu_load])
}

decision := {
    "allow": allow,
    "domain": "infrastructure",
    "reasons": reasons,
    "violations": vs,
    "observed": {
        "disk_free_gb": disk_free_gb,
        "cpu_load": cpu_load,
    },
} if {
    vs := [v | v := violation[_]]
    allow := count(vs) == 0
    reasons := ["Infrastructure policy checks passed"]
    allow
}

decision := {
    "allow": false,
    "domain": "infrastructure",
    "reasons": reasons,
    "violations": vs,
    "observed": {
        "disk_free_gb": disk_free_gb,
        "cpu_load": cpu_load,
    },
} if {
    vs := [v | v := violation[_]]
    count(vs) > 0
    reasons := [r | r := vs[_]]
}
