# Manage Services

## List Services

```bash
cb list
cb list --json
```

Discovered services are visible even when the broker is not running.

## Enable or Disable Autostart

```bash
cb enable presto
cb disable presto
```

Use `--start` or `--stop` to combine the state change with process action:

```bash
cb enable presto --start
cb disable presto --stop
```

## Start and Stop

```bash
cb start
cb start presto
cb stop presto
cb stop
```

`cb start` starts the broker and enabled services. `cb stop` without names
shuts the broker down.

## Restart

```bash
cb restart presto
cb restart
```

Restarting a named service keeps the broker running. Restarting without
names stops and starts the broker process.
