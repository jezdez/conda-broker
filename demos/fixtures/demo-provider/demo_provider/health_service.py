"""Long-running demo service used by the health-check tape."""

from __future__ import annotations

import time


def main() -> None:
    print("health demo ready", flush=True)
    count = 0
    while True:
        count += 1
        print(f"health demo heartbeat {count}", flush=True)
        time.sleep(1)


if __name__ == "__main__":
    main()
