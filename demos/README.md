# conda-broker Demos

The demos are VHS tape sources. Record all demos with:

```bash
pixi run demos
```

Record one demo with:

```bash
pixi run demos quickstart
```

The tapes install the fixture provider from `demos/fixtures/demo-provider`
into the Pixi development environment, then use temporary runtime and log
directories under `/tmp`.

The `health-check` demo uses an exec health check that exits non-zero on the
first check and zero afterwards. That shows the broker stopping the old process,
scheduling a restart, and reporting the resulting events.
