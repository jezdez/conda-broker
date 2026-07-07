# Configure Health Checks

Health checks control how the broker decides whether a process is healthy.
They are observed by the broker monitor after a process starts and then at
the configured interval.

![health check demo](../../demos/health-check.gif)

## Lifecycle

A newly started service reports `health="unknown"` until a check passes or
the startup period expires. A passing check changes it to `healthy`. A
failing check during `start_period_s` keeps the service in `starting`; a
failing check after that period changes it to `unhealthy`.

`cb start` is not a readiness gate. It returns after the process is started
and the first health check may run shortly afterwards. Use `cb wait SERVICE`
when a script needs a ready service, and `cb status SERVICE` to inspect the
current health state.

When a check fails:

- `restart_policy="never"` leaves the process state visible as unhealthy
  and does not restart it.
- `restart_policy="on-failure"` or `"always"` emits `service.unhealthy`,
  stops the process with the configured graceful stop behavior, and schedules
  a restart with exponential backoff.
- The scheduled restart emits `service.restart_scheduled` with
  `data.reason == "health"`.

## Process Health

```python
HealthCheck(type="process")
```

The process is healthy while the child process is still alive.

## TCP Health

```python
HealthCheck(type="tcp", host="127.0.0.1", port=8765, interval_s=5, timeout_s=1)
```

Use TCP checks for services with a local socket but no HTTP endpoint.

If the service declares an endpoint, bind the check to that endpoint:

```python
HealthCheck(type="tcp", endpoint="default", interval_s=5, timeout_s=1)
```

## HTTP Health

```python
HealthCheck(type="http", url="http://127.0.0.1:8765/health")
```

HTTP status codes from 200 through 499 are considered reachable.

Endpoint-bound HTTP checks use the resolved endpoint URL:

```python
HealthCheck(type="http", endpoint="default", interval_s=5, timeout_s=1)
```

## Exec Health

```python
HealthCheck(type="exec", command=("python", "-m", "my_provider.healthcheck"))
```

Use exec checks for custom local validation. Keep them fast, deterministic,
and side-effect-light.

Exec health checks run as local commands from the broker process
environment. Prefer absolute commands or provider-controlled module
commands, and keep timeouts short so a stuck health check cannot delay other
service monitoring.

## Startup Period

The default `start_period_s` is five seconds. During that period, failing
checks do not restart the service. This matters for services that need a
moment to bind a dynamically assigned endpoint port.

```python
HealthCheck(type="http", endpoint="default", start_period_s=10)
```

Set `start_period_s=0` when the first failed check should immediately count
as an unhealthy service.
