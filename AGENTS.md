# AGENTS.md - conda-broker coding guidelines

## Project structure

- `conda_broker/plugin.py` is imported on every conda invocation and
  must stay lazy. Do not import CLI, supervisor, registry, or runtime
  modules at module import time.
- `conda_broker/cli/main.py` owns parser configuration and dispatch.
  Subcommands live in `conda_broker/cli/services/`.
- Root modules own shared behavior: `models.py`, `registry.py`,
  `state.py`, `paths.py`, `ipc.py`, `logs.py`, `supervisor.py`,
  `client.py`, `broker.py`, `exceptions.py`, and `hookspec.py`.
- Runtime implementations live under `conda_broker/runtimes/`.
  `process.py` is the local host-process backend.

## Code style

- Use relative imports for intra-package references.
- Keep dependencies small. Prefer stdlib unless a declared dependency
  materially improves the public surface.
- Use `from __future__ import annotations` in every module.
- Use modern annotations (`str | None`, `list[str]`).
- Avoid `unittest.mock`; tests use pytest fixtures, monkeypatch, and
  small real fakes.

## Conda integration

- Conda only loads the `conda broker` subcommand and broker settings.
  Provider service discovery is owned by `conda-broker` through its
  own pluggy project (`conda_broker`).
- The broker must not start implicitly during arbitrary conda commands.
- Runtime and log defaults live below conda's app namespace:
  `platformdirs.user_runtime_dir("conda") / "broker"` and
  `platformdirs.user_log_dir("conda") / "broker"`.
- The package exposes `cb` as the short command. Keep `cb start`,
  `cb status`, and `cb logs <service>` as the compact workflow.

## Verification

- After code changes, run `pixi run -e test pytest`,
  `pixi run ruff check`, `pixi run ruff format --check`, and
  `pixi run ty check conda_broker` when available.
