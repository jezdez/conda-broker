# conda-broker Demos

The demos are VHS tape sources. Record all demos with:

```bash
pixi run demos
```

Record one demo with:

```bash
pixi run demos quickstart
```

Validate tape sources, fixture services, tracked GIFs, and documentation
references without recording a terminal session:

```bash
pixi run demo-check
```

The Pixi recorder exposes the fixture provider from
`demos/fixtures/demo-provider` through an isolated import path, stops any prior
demo broker, and prepares isolated runtime and log directories under `/tmp`
before VHS starts. It does not modify the Pixi environment. Setup is kept
outside the tape so recordings begin with the first user-facing command.

The `health-check` demo uses an exec health check that exits non-zero on the
first check and zero afterwards. That shows the broker stopping the old process,
scheduling a restart, and reporting the resulting events.
