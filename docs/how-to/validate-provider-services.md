# Validate Provider Services

Use the development conformance harness before shipping a provider plugin.
It loads services through the real `ServiceRegistry`, then runs checks in
temporary runtime and log directories so your normal broker state is not
touched.

## Validate the Spec

```bash
cb dev validate my-provider.api
```

This checks that the service is discoverable, has a supported runtime,
uses an executable-looking command, has known dependencies, and defines a
usable health check.

## Smoke-Test the Process

```bash
cb dev run my-provider.api
```

`run` starts the service, observes it briefly, checks status and health,
captures recent logs and events, and stops it again.

Use `--duration` when the service needs a little time to produce useful
logs:

```bash
cb dev run my-provider.api --duration 10
```

## Test Runtime Scenarios

Start and stop:

```bash
cb dev test my-provider.api --scenario start-stop
```

Health check:

```bash
cb dev test my-provider.api --scenario health
```

Crash restart policy:

```bash
cb dev test my-provider.api --scenario crash
```

The crash scenario kills the target child process in an isolated
workspace. Services with `restart_policy="on-failure"` or `"always"` must
restart. Services with `restart_policy="never"` must stay stopped.

## Produce a Report

```bash
cb dev report my-provider.api
cb dev report my-provider.api --json
```

The report runs static validation, a smoke run, a health scenario, and a
crash scenario. JSON output is suitable for CI.

## Keep the Workspace

By default, conformance workspaces are deleted. Keep one when you need to
inspect the generated runtime files and logs:

```bash
cb dev test my-provider.api --scenario crash --keep
```

The human output prints the workspace path when it is kept.
