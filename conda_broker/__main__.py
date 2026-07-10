"""Standalone CLI entry point for ``cb``."""

from __future__ import annotations


def main(args: list[str] | None = None) -> None:
    import sys
    from pathlib import Path

    from .cli.main import execute_broker, generate_broker_parser

    parser = generate_broker_parser()
    if args is None:
        parser.prog = Path(sys.argv[0]).name
    parsed = parser.parse_args(args)
    raise SystemExit(execute_broker(parsed, parser=parser))


if __name__ == "__main__":
    main()
