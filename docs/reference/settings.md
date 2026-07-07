# Settings

`conda-broker` registers conda settings lazily.

## `broker_runtime_dir`

Runtime directory for broker state:

```yaml
broker_runtime_dir: /path/to/runtime
```

Alias:

```yaml
conda_broker_runtime_dir: /path/to/runtime
```

## `broker_log_dir`

Log directory for broker and service logs:

```yaml
broker_log_dir: /path/to/logs
```

Alias:

```yaml
conda_broker_log_dir: /path/to/logs
```

Explicit CLI or API paths take precedence over environment variables.
Environment variables `CONDA_BROKER_RUNTIME_DIR` and `CONDA_BROKER_LOG_DIR`
take precedence over conda settings, and conda settings take precedence over
platform defaults.
