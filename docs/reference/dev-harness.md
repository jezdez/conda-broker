# Development Harness

`cb dev` is for provider authors. It never uses the user's normal broker
process. Runtime state and logs are created under a temporary workspace for
each run unless `--keep` is used.

## Commands

- `cb dev validate SERVICE`: static service-spec checks only.
- `cb dev run SERVICE`: start, observe, collect logs/events, and stop.
- `cb dev test SERVICE --scenario start-stop`: lifecycle smoke test.
- `cb dev test SERVICE --scenario health`: observe the configured health
  check.
- `cb dev test SERVICE --scenario crash`: kill the target child process and
  verify restart policy.
- `cb dev report SERVICE`: run validation, smoke, health, and crash checks.

## Check Status

Each check has one of these statuses:

- `pass`: the service satisfied the check.
- `warn`: the service may still work, but the provider should review the
  finding.
- `skip`: the check was intentionally not applicable.
- `fail`: the service failed conformance and the command exits non-zero.

Warnings do not make the report fail. Failures do.

## JSON Shape

Single-result commands return:

```json
{
  "conformance": {
    "ok": true,
    "service": "my-provider.api",
    "command": "test",
    "scenario": "health",
    "workspace": "/tmp/conda-broker-dev-abcd",
    "kept": false,
    "checks": [
      {
        "name": "health.observed",
        "status": "pass",
        "message": "health check reported healthy",
        "data": {}
      }
    ],
    "status": {
      "name": "my-provider.api",
      "state": "ready",
      "running": true,
      "health": "healthy",
      "ready": true,
      "restart_count": 0,
      "endpoints": {
        "default": {
          "name": "default",
          "protocol": "http",
          "host": "127.0.0.1",
          "port": 8765,
          "path": "/health",
          "url": "http://127.0.0.1:8765/health"
        }
      }
    },
    "events": [],
    "logs": []
  }
}
```

`cb dev report --json` returns:

```json
{
  "ok": true,
  "service": "my-provider.api",
  "command": "report",
  "results": []
}
```

Each result in `results` has the same shape as the single-result
`conformance` object.

Endpoint-aware services get additional checks such as
`endpoint.declared`, `endpoint.resolved`, and `endpoint.reachable`.
