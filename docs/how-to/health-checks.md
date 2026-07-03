# Configure Health Checks

Health checks control how the broker decides whether a process is healthy.
Unhealthy services are stopped and restarted according to their
`restart_policy`.

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

## HTTP Health

```python
HealthCheck(type="http", url="http://127.0.0.1:8765/health")
```

HTTP status codes below 500 are considered reachable.

## Exec Health

```python
HealthCheck(type="exec", command=("python", "-m", "my_provider.healthcheck"))
```

Use exec checks for custom local validation. Keep them fast, deterministic,
and side-effect-light.
