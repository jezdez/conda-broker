# Configure Paths

By default, runtime and log data live under conda's application namespace:

- runtime: `platformdirs.user_runtime_dir("conda") / "broker"`
- logs: `platformdirs.user_log_dir("conda") / "broker"`

The exact platform base directory depends on the operating system.

Path resolution uses this precedence:

1. Explicit `--runtime-dir` and `--log-dir` CLI options, or explicit
   `ServicePaths` passed to the Python API.
2. `CONDA_BROKER_RUNTIME_DIR` and `CONDA_BROKER_LOG_DIR`.
3. Conda settings.
4. Platform defaults.

## CLI Overrides

```bash
cb --runtime-dir /tmp/conda-broker-runtime --log-dir /tmp/conda-broker-logs status
cb status --runtime-dir /tmp/conda-broker-runtime --log-dir /tmp/conda-broker-logs
```

## Environment Variables

```bash
export CONDA_BROKER_RUNTIME_DIR=/tmp/conda-broker-runtime
export CONDA_BROKER_LOG_DIR=/tmp/conda-broker-logs
```

## Conda Settings

`conda-broker` registers these settings:

```yaml
broker_runtime_dir: /tmp/conda-broker-runtime
broker_log_dir: /tmp/conda-broker-logs
```

Settings are loaded lazily with the conda plugin and do not start the broker.

Configured paths expand `~` and are normalized to absolute paths without
following a configured directory symlink. On POSIX, pre-existing runtime and
log directories must be owned by the current user with mode `0700`. Fix an
unsafe directory explicitly; the broker will not change permissions on a
directory it did not create.
