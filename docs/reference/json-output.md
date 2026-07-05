# JSON Output

Commands that report state support `--json`. JSON output is intended for
automation and remains separate from Rich human output.

![JSON status demo](../../demos/json-status.gif)

## Status

```json
{
  "broker": {
    "running": true,
    "started": false
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
      "endpoints": [
        {
          "name": "default",
          "protocol": "http",
          "host": "127.0.0.1",
          "port": 17654,
          "path": "/health",
          "port_env": null,
          "url_env": null
        }
      ]
    }
  ],
  "enabled": ["package-cache"]
}
```

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
