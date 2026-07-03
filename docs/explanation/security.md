# Security

The broker is local-first and user-scoped.

- IPC listens only on localhost.
- The auth token is generated per broker process.
- Connection info is written to a runtime file with restrictive permissions
  where the platform supports it.
- Clients reject server-file hosts that do not resolve to loopback, so a
  tampered runtime file cannot redirect broker requests to a remote host.
- Query helpers do not start the broker as a side effect.
- Provider plugins must be installed Python packages; discovery uses Python
  entry points.
- Child services inherit the user's permissions. Providers should bind local
  APIs to `127.0.0.1` unless they have a clear reason not to.

Service specs are code, not untrusted configuration. Installing a provider
plugin means trusting that package's Python code.

Future container runtimes would have different security properties from host
processes. They should define explicit process, network, filesystem, and
credential boundaries before becoming part of the public provider API.
