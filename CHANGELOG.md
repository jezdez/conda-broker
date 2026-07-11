# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.1] - 2026-07-11

### Fixed

- Let service readiness waits use their requested timeout for broker IPC.

## [0.1.0] - 2026-07-11

### Added

- User-controlled supervision for long-running conda-adjacent services through
  `conda broker` and the compact `cb` command.
- Provider discovery, service readiness contracts, restart policies, health
  checks, structured events, logs, and a public `Broker` API.
- Plugin-owned broker-subcommand helpers and a provider conformance harness.
- Diataxis documentation: tutorials, how-to guides, reference, and
  explanations.
- Tag-driven, attested PyPI releases using trusted publishing and immutable
  GitHub Release assets.
