"""Flaky demo process."""

from __future__ import annotations

import os
import pathlib
import sys
import time

state_file = pathlib.Path(
    os.environ.get("CONDA_BROKER_DEMO_FLAKY_STATE", "/tmp/conda-broker-demo-flaky")
)
count = int(state_file.read_text()) if state_file.exists() else 0
state_file.write_text(str(count + 1))
if count == 0:
    print("flaky exits once", flush=True)
    sys.exit(7)

print("flaky recovered", flush=True)
while True:
    time.sleep(1)
