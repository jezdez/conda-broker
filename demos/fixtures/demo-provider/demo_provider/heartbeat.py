"""Heartbeat demo process."""

from __future__ import annotations

import itertools
import time

print("heartbeat ready", flush=True)
for index in itertools.count(1):
    print(f"heartbeat tick {index}", flush=True)
    time.sleep(1)
