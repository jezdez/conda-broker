# Prior Art

`conda-broker` overlaps with process managers, Procfile runners, and local
developer service tools, but its integration point is different.

## Honcho and Procfile Runners

Honcho is a Python Procfile runner inspired by Foreman. It is useful for
starting a set of processes together, but it is centered on a Procfile and a
foreground terminal session. `conda-broker` needs provider discovery,
persisted enabled state, status queries from plugins, structured events,
JSON output, and a user-scoped broker.

## Circus

Circus provides process supervision and sockets. It is broader than the
broker's immediate needs and would introduce a second control plane. The
broker keeps process control in Python stdlib code so the conda plugin can
own the API and lifecycle.

## Supervisor

Supervisor is mature and widely used for Unix process supervision. It is
less suitable as the direct core here because `conda-broker` needs a Python
provider model, cross-platform behavior, and conda plugin packaging.

## Mirakuru

Mirakuru is useful for test-time process orchestration. The broker needs a
long-lived user service model, CLI oversight, persistent state, logs, and
events.

## Why Build the Broker Layer

The broker is not trying to replace system service managers. It is a conda
plugin platform for conda-adjacent services that users can see and manage
from conda tooling.
