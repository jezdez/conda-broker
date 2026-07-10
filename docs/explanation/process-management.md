# Process Management

The local runtime uses Python's standard library process tools.

![restart policy demo](../../demos/restart-policy.gif)

- `subprocess.Popen` starts child services.
- On POSIX, services start in a new session so signals can target the
  service process group.
- On Windows, graceful and forced fallback paths use `taskkill /T` so child
  process trees are included.
- Stops use the configured signal, then a grace-period wait, then kill as a
  fallback.
- Restart policy supports `never`, `on-failure`, and `always`.
- Exponential backoff is capped at 60 seconds and resets after five continuous
  minutes in the healthy state.
- Health checks support process, TCP, HTTP, and exec checks.
- Endpoint declarations let the broker allocate local ports, inject endpoint
  environment variables, and report resolved URLs.

Service state is readiness-oriented:

- `starting`: the process is running but no health check has passed yet.
- `ready`: the process is running and its health check is healthy.
- `degraded`: the process is running but health is unhealthy.
- `stopping`: a graceful stop is in progress and readiness is false.
- `backing-off`: a restart is scheduled after a crash or health failure.
- `stopped`: no process is running.

During `HealthCheck.start_period_s`, failed checks keep the service in
`starting` instead of restarting it. After that period, a failed check is
treated as the restart trigger. The broker emits `service.unhealthy`, asks
the process to stop, waits for the configured grace period, kills it if
needed, closes the old process record, and schedules a restart according to
the service's restart policy and backoff state.

The broker records each managed PID together with its process creation time
and broker instance ID. Graceful broker shutdown stops managed process groups.
If the broker is killed, its successor compares both PID and creation time
before terminating an orphan, which avoids killing an unrelated process after
PID reuse. Startup bookkeeping is transactional: if the process journal
cannot be written, the new child is killed instead of becoming untracked.

Service stdout and stderr flow through a dedicated capture thread. Rotation
happens while a service is running, and the reader continues draining output
if opening, rotating, or writing a log fails so the child cannot block on a
full pipe.

Enabled services autostart independently. A launch failure is recorded as
`service.start_failed`; it does not shut down the broker or skip later enabled
services.

This keeps the broker portable across Linux, macOS, and Windows without
committing the public API to container runtime behavior before it exists.

The broker intentionally does not wrap Honcho, Circus, Supervisor,
Mirakuru, or a Procfile runner. Those tools are useful, but `conda-broker`
needs a conda plugin API, provider discovery, user-scoped paths, JSON
contracts, and provider-facing status helpers more than a generic process
manager API.
