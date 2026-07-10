# JSON Output

Commands that report state support `--json`. JSON output is intended for
automation and remains separate from Rich human output.

![JSON status demo](../../demos/json-status.gif)

## Status

```json
{
  "broker": {
    "running": true
  },
  "services": [
    {
      "name": "package-cache",
      "summary": "Local conda package metadata cache",
      "source": "conda-package-cache",
      "runtime": "process",
      "enabled": true,
      "state": "ready",
      "running": true,
      "pid": 12345,
      "exit_code": null,
      "started_at": "2026-07-03T12:00:00+00:00",
      "restart_count": 0,
      "health": "healthy",
      "ready": true,
      "endpoints": {
        "default": {
          "name": "default",
          "protocol": "http",
          "host": "127.0.0.1",
          "port": 17654,
          "path": "/health",
          "url": "http://127.0.0.1:17654/health"
        }
      }
    }
  ]
}
```

`cb start SERVICE --json` uses the same status rows and adds two ownership
fields: `broker.started` says whether this command launched the broker, and
the top-level `started` list contains requested services newly launched by
this call. Context managers use those fields to avoid stopping pre-existing
work.

## List

```json
{
  "services": [
    {
      "name": "package-cache",
      "summary": "Local conda package metadata cache",
      "source": "conda-package-cache",
      "runtime": "process",
      "start_policy": "manual",
      "restart_policy": "on-failure",
      "health_check": {
        "type": "http",
        "interval_s": 30.0,
        "timeout_s": 5.0,
        "start_period_s": 5.0,
        "endpoint": "default",
        "command": [],
        "host": null,
        "port": null,
        "url": null
      },
      "endpoints": [
        {
          "name": "default",
          "protocol": "http",
          "host": "127.0.0.1",
          "port": null,
          "path": "/health",
          "port_env": "CONDA_PACKAGE_CACHE_PORT",
          "url_env": null
        }
      ],
      "dependencies": [],
      "env": {},
      "cwd": null,
      "process": {
        "argv": ["python", "-m", "conda_package_cache", "--serve"],
        "env": {},
        "cwd": null,
        "stop_signal": "TERM",
        "grace_period_s": 5.0
      }
    }
  ],
  "enabled": ["package-cache"],
  "provider_errors": []
}
```

Provider failures do not suppress healthy services. Each `provider_errors`
entry reports `provider`, `phase`, `error`, and `error_type`.

## Endpoint

```json
{
  "service": "package-cache",
  "endpoint_name": "default",
  "endpoint": {
    "name": "default",
    "protocol": "http",
    "host": "127.0.0.1",
    "port": 17654,
    "path": "/health",
    "url": "http://127.0.0.1:17654/health"
  },
  "endpoints": {
    "default": {
      "name": "default",
      "protocol": "http",
      "host": "127.0.0.1",
      "port": 17654,
      "path": "/health",
      "url": "http://127.0.0.1:17654/health"
    }
  },
  "ready": true
}
```

## Wait

`cb wait SERVICE --json` returns the same `services` status envelope as
`cb status SERVICE`. The command exits zero only when the first service in
the envelope has `ready: true`.

## Logs Follow

`cb logs SERVICE --follow --json` emits JSON Lines:

```json
{"service": "package-cache", "line": "ready"}
{"service": "package-cache", "line": "served numpy metadata"}
```

## Events Follow

`cb events --follow --json` emits one event object per line.

## Development Harness

`cb dev validate`, `cb dev run`, and `cb dev test` return one
`conformance` object. `cb dev report` returns a report object with a
`results` list. See [](dev-harness.md) for the full shape.

## Errors

Commands that fail with a broker-domain error and `--json` emit:

```json
{"error": "Unknown service: missing", "ok": false}
```

They also exit non-zero.
