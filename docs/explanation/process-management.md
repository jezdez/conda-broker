# Process Management

The local runtime uses Python's standard library process tools.

![restart policy demo](../../demos/restart-policy.gif)

- `subprocess.Popen` starts child services.
- On POSIX, services start in a new session so signals can target the
  service process group.
- Stops use the configured signal, then a grace-period wait, then kill as a
  fallback.
- Restart policy supports `never`, `on-failure`, and `always`.
- Exponential backoff is capped at 60 seconds and resets after a sustained
  healthy run.
- Health checks support process, TCP, HTTP, and exec checks.
- Endpoint declarations let the broker allocate local ports, inject endpoint
  environment variables, and report resolved URLs.

Service state is readiness-oriented:

- `starting`: the process is running but no health check has passed yet.
- `ready`: the process is running and its health check is healthy.
- `degraded`: the process is running but health is unhealthy.
- `backing-off`: a restart is scheduled after a crash or health failure.
- `stopped`: no process is running.

During `HealthCheck.start_period_s`, failed checks keep the service in
`starting` instead of restarting it. After that period, a failed check is
treated as the restart trigger. The broker emits `service.unhealthy`, asks
the process to stop, waits for the configured grace period, kills it if
needed, closes the old process record, and schedules a restart according to
the service's restart policy and backoff state.

This keeps the broker portable across Linux, macOS, and Windows without
committing the public API to container runtime behavior before it exists.

The broker intentionally does not wrap Honcho, Circus, Supervisor,
Mirakuru, or a Procfile runner. Those tools are useful, but `conda-broker`
needs a conda plugin API, provider discovery, user-scoped paths, JSON
contracts, and provider-facing status helpers more than a generic process
manager API.
