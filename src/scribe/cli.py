import argparse
from pathlib import Path
from typing import Sequence

from scribe import __version__


PLUGIN_ROOT = Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scribe")
    parser.add_argument(
        "--version",
        action="version",
        version=f"scribe {__version__} ({PLUGIN_ROOT})",
    )
    parser.add_subparsers(dest="command")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    return 0
