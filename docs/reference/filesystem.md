# Filesystem Layout

Runtime data defaults to `platformdirs.user_runtime_dir("conda") / "broker"`:

- `server.json`: localhost IPC connection info, token, PID, and instance ID
- `broker.pid`: broker process ID and instance ID
- `broker.lock`: one-broker-per-user advisory lock and owner metadata
- `broker.start.lock`: serializes concurrent broker start requests
- `state.lock`: shared lock for enabled-state and event writes
- `enabled.json`: user enabled service set
- `processes.json`: managed PID, creation time, and broker instance records
- `events.jsonl`: append-only event records
- `events.jsonl.1`: previous rotated event records

Log data defaults to `platformdirs.user_log_dir("conda") / "broker"`:

- `broker.log`: broker stdout and stderr
- `<service>.log`: service stdout and stderr
- `<service>.log.1`: previous rotated service log

Runtime and log directories are created with user-only permissions where the
platform supports it. Private files are written with user-readable-only
permissions. On POSIX, existing directories with a different owner or mode
other than `0700` are rejected rather than modified.

Lock files are persistent metadata: they normally remain after the broker
stops. Lock ownership, not file existence or age, determines whether a broker
is running or starting. `server.json` and `broker.pid` are removed only by the
broker instance that wrote them.
