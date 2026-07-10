"""Small long-running process used by broker integration tests."""

from __future__ import annotations

import time

print("integration heartbeat ready", flush=True)
while True:
    time.sleep(0.1)
