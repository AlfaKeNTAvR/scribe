import argparse
import json
from pathlib import Path
from typing import Sequence

from scribe import __version__
from scribe.record import Record
from scribe.schema import Problem, validate_record
from scribe.store import Store


PLUGIN_ROOT = Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scribe")
    parser.add_argument(
        "--version",
        action="version",
        version=f"scribe {__version__} ({PLUGIN_ROOT})",
    )
    subparsers = parser.add_subparsers(dest="command")
    validate = subparsers.add_parser("validate", help="validate decision records")
    validate.add_argument("paths", nargs="*")
    validate.add_argument("--no-attestation", action="store_true")
    validate.add_argument("--json", action="store_true", dest="as_json")
    return parser


def _record_paths(values: Sequence[str]) -> tuple[list[Path], Store | None]:
    if not values:
        store = Store.discover()
        return (sorted(store.path.glob("D-*.md")), store) if store else ([], None)
    paths: list[Path] = []
    for value in values:
        path = Path(value)
        if path.is_dir():
            paths.extend(sorted(path.glob("D-*.md")))
        else:
            paths.append(path)
    store = None
    directories = {path.resolve().parent for path in paths}
    if len(directories) == 1:
        directory = next(iter(directories))
        if directory.name == "decisions" and directory.parent.name == "docs":
            store = Store(directory)
    return paths, store


def _validate_command(args: argparse.Namespace) -> int:
    paths, store = _record_paths(args.paths)
    results: list[tuple[Path, Problem]] = []
    for path in paths:
        try:
            record = Record.load(path)
            problems = validate_record(
                record.data,
                record.body,
                store=store,
                path=path,
                check_attestation=not args.no_attestation,
            )
        except (OSError, ValueError) as exc:
            problems = [Problem("error", "parse_error", str(exc))]
        results.extend((path, problem) for problem in problems)
    errors = sum(problem.severity == "error" for _, problem in results)
    warnings = sum(problem.severity == "warning" for _, problem in results)
    if args.as_json:
        print(json.dumps({
            "records": len(paths),
            "errors": errors,
            "warnings": warnings,
            "problems": [
                {"path": str(path), **problem.__dict__} for path, problem in results
            ],
        }))
    else:
        for path, problem in results:
            print(f"{path}: {problem.severity}: {problem.code}: {problem.message}")
        print(f"{len(paths)} records, {errors} errors, {warnings} warnings")
    return 1 if errors else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "validate":
        return _validate_command(args)
    return 0
