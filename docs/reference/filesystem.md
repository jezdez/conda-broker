# Filesystem Layout

Runtime data defaults to `platformdirs.user_runtime_dir("conda") / "broker"`:

- `server.json`: localhost IPC connection info and token
- `broker.pid`: broker process ID
- `broker.lock`: one-broker-per-user lock file
- `state.lock`: shared lock for enabled-state and event writes
- `enabled.json`: user enabled service set
- `events.jsonl`: append-only event records
- `events.jsonl.1`: previous rotated event records

Log data defaults to `platformdirs.user_log_dir("conda") / "broker"`:

- `broker.log`: broker stdout and stderr
- `<service>.log`: service stdout and stderr
- `<service>.log.1`: previous rotated service log

Runtime and log directories are created with user-only permissions where the
platform supports it. Private files are written with user-readable-only
permissions.
