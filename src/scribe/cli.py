import argparse
import json
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from scribe import __version__
from scribe.index import check_index, write_index
from scribe.lookup import lookup
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
    index_parser = subparsers.add_parser(
        "index",
        help="generate docs/decisions/INDEX.md",
    )
    index_parser.add_argument("path", nargs="?", help="store or repository root")
    index_parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 when INDEX.md differs from the generated text",
    )
    lookup_parser = subparsers.add_parser(
        "lookup",
        help="reverse lookup between commits and decision records",
    )
    lookup_parser.add_argument("token", help="commit-ish, ULID or alias")
    new_parser = subparsers.add_parser(
        "new",
        help="write a decision record from a JSON spec",
    )
    new_parser.add_argument("--spec", required=True, help="path to the JSON spec file")
    new_parser.add_argument(
        "--by", help="author recorded in the proposed history entry"
    )
    new_parser.add_argument("--session", help="Claude Code session id")
    new_parser.add_argument(
        "--register",
        action="store_true",
        help="add the new ULID to the session's pending decisions",
    )
    for verb in ("ratify", "reject"):
        verdict_parser = subparsers.add_parser(
            verb,
            help=f"record a human {verb} verdict on a decision (plan 3.8, 4.10)",
        )
        verdict_parser.add_argument("record", help="alias or ULID")
        verdict_parser.add_argument(
            "words",
            nargs="*",
            help="free-text note (the skills pass it after the alias)",
        )
        verdict_parser.add_argument(
            "--by", help="who decided; default from git user.name"
        )
        verdict_parser.add_argument(
            "--note", help="note stored on the attestation line"
        )
        verdict_parser.add_argument(
            "--at", type=_utc_stamp, help="ISO 8601 UTC, YYYY-MM-DDTHH:MM:SSZ"
        )
        verdict_parser.add_argument(
            "--via",
            choices=("skill", "cli", "hand-written"),
            default="cli",
            help="path the verdict came through (default cli)",
        )
    hook_parser = subparsers.add_parser(
        "hook",
        help="run a Claude Code hook handler with the JSON payload on stdin",
    )
    hook_parser.add_argument("event", help="hook event name from hooks/hooks.json")
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
        print(
            json.dumps(
                {
                    "records": len(paths),
                    "errors": errors,
                    "warnings": warnings,
                    "problems": [
                        {"path": str(path), **problem.__dict__}
                        for path, problem in results
                    ],
                }
            )
        )
    else:
        for path, problem in results:
            print(f"{path}: {problem.severity}: {problem.code}: {problem.message}")
        print(f"{len(paths)} records, {errors} errors, {warnings} warnings")
    return 1 if errors else 0


def _index_command(args: argparse.Namespace) -> int:
    store = Store(args.path) if args.path else Store.discover()
    if store is None or not store.path.is_dir():
        print("no decision store found (docs/decisions)")
        return 1
    if args.check:
        target, up_to_date = check_index(store)
        if up_to_date:
            print(f"{_display_path(store, target)} is up to date")
            return 0
        print(f"{_display_path(store, target)} is out of date, run scribe index")
        return 1
    target, changed = write_index(store)
    action = "wrote" if changed else "unchanged"
    print(f"{action} {_display_path(store, target)}, {len(store.records())} records")
    return 0


def _display_path(store: Store, target: Path) -> str:
    try:
        return target.relative_to(store.root).as_posix()
    except ValueError:
        return target.as_posix()


def _lookup_command(args: argparse.Namespace) -> int:
    store = Store.discover()
    if store is None:
        print("no decision store found (docs/decisions)")
        return 1
    lines, status = lookup(args.token, store)
    for line in lines:
        print(line)
    return status


def _new_command(args: argparse.Namespace) -> int:
    from scribe.newrecord import SpecError, create_record, load_spec

    store = Store.discover()
    if store is None or not store.path.is_dir():
        print("no decision store found (docs/decisions)")
        return 1
    try:
        spec = load_spec(args.spec)
    except SpecError as exc:
        print(f"{args.spec}: {exc}")
        return 1
    path, problems = create_record(
        store,
        spec,
        by=args.by,
        session=args.session,
        register=args.register,
    )
    for problem in problems:
        print(f"{problem.severity}: {problem.code}: {problem.message}")
    if path is None:
        print("no record written")
        return 1
    print(_display_path(store, path))
    return 0


def _utc_stamp(value: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DDTHH:MM:SSZ") from exc
    return value


def _verdict_command(args: argparse.Namespace) -> int:
    from scribe.ratify import apply_verdict, normalize_by

    store = Store.discover()
    if store is None or not store.path.is_dir():
        print("no decision store found (docs/decisions)")
        return 1
    note = " ".join(part for part in (args.note, " ".join(args.words)) if part) or None
    try:
        outcome = apply_verdict(
            store,
            args.record,
            args.command,
            by=normalize_by(args.by, store.root),
            note=note,
            at=args.at,
            via=args.via,
        )
    except OSError as exc:
        print(f"scribe {args.command} failed: {exc}; re-run the same command to finish")
        return 1
    print(outcome.message)
    return outcome.code


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "validate":
        return _validate_command(args)
    if args.command == "index":
        return _index_command(args)
    if args.command == "lookup":
        return _lookup_command(args)
    if args.command == "new":
        return _new_command(args)
    if args.command in ("ratify", "reject"):
        return _verdict_command(args)
    if args.command == "hook":
        from scribe.hooks.launcher import dispatch

        return dispatch(args.event)
    return 0
