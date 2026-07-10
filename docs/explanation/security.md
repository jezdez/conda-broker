# Security

The broker is local-first and user-scoped.

- IPC listens only on localhost.
- The auth token is generated per broker process.
- IPC requests and responses are limited to 1 MiB, and idle request reads time
  out after five seconds.
- Connection info is written to a runtime file with restrictive permissions
  where the platform supports it.
- Clients reject server-file hosts that do not resolve to loopback, so a
  tampered runtime file cannot redirect broker requests to a remote host.
- Query helpers do not start the broker as a side effect.
- Provider plugins must be installed Python packages; discovery uses Python
  entry points.
- Child services inherit the user's permissions. Providers should bind local
  APIs to `127.0.0.1` unless they have a clear reason not to.
- On POSIX, existing runtime and log directories are rejected unless they are
  owned by the current user with mode `0700`; the broker does not silently
  loosen or rewrite their permissions.
- Broker ownership uses a lifetime advisory lock. PID metadata also carries a
  random instance ID so an older process cannot delete a successor's files.
- A separate advisory startup lock gives concurrent clients one lifecycle
  owner, so context managers do not stop a broker started by another client.
- Orphan cleanup matches both PID and process creation time before sending a
  signal.

Service specs are code, not untrusted configuration. Installing a provider
plugin means trusting that package's Python code.

The IPC token authenticates local broker commands; it does not add
authentication to provider service endpoints. A provider that binds beyond
loopback must define its own network and authentication policy. Dynamic port
selection narrows collisions but cannot make the interval between releasing
the reservation and the child binding it atomic; providers should fail fast
on bind errors so restart policy can allocate a fresh port.

Windows does not expose POSIX ownership and mode checks. Runtime files remain
inside the user-scoped platform directory, but installations that need strong
multi-user isolation should also enforce appropriate Windows ACLs.

Future container runtimes would have different security properties from host
processes. They should define explicit process, network, filesystem, and
credential boundaries before becoming part of the public provider API.
