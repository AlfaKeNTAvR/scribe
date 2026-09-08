from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import yaml


class FrontMatterError(ValueError):
    pass


class _FlowMap(dict):
    pass


class _Dumper(yaml.SafeDumper):
    pass


def _represent_flow_map(dumper: yaml.SafeDumper, value: _FlowMap) -> yaml.Node:
    return dumper.represent_mapping("tag:yaml.org,2002:map", value, flow_style=True)


def _represent_date(dumper: yaml.SafeDumper, value: date) -> yaml.Node:
    return dumper.represent_scalar("tag:yaml.org,2002:str", value.isoformat())


def _represent_datetime(dumper: yaml.SafeDumper, value: datetime) -> yaml.Node:
    return dumper.represent_scalar("tag:yaml.org,2002:str", _datetime_text(value))


_Dumper.add_representer(_FlowMap, _represent_flow_map)
_Dumper.add_representer(date, _represent_date)
_Dumper.add_representer(datetime, _represent_datetime)


def _datetime_text(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    value = value.astimezone(timezone.utc)
    return value.replace(tzinfo=None).isoformat(timespec="seconds") + "Z"


def _normalize(value: Any) -> Any:
    if isinstance(value, datetime):
        return _datetime_text(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items()}
    return value


def split(text: str) -> tuple[dict[str, Any], str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.startswith("---\n"):
        raise FrontMatterError("missing opening front matter delimiter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise FrontMatterError("missing closing front matter delimiter")
    try:
        loaded = yaml.safe_load(text[4:end])
    except yaml.YAMLError as exc:
        raise FrontMatterError(f"invalid YAML: {exc}") from exc
    if not isinstance(loaded, dict):
        raise FrontMatterError("front matter must be a mapping")
    body = text[end + 5 :]
    return _normalize(loaded), body


def join(mapping: dict[str, Any], body: str) -> str:
    prepared: dict[str, Any] = {}
    flow_keys = {"history", "affects", "implementation_links", "verify"}
    for key, value in mapping.items():
        if key in flow_keys and isinstance(value, list):
            prepared[key] = [
                _FlowMap(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            prepared[key] = value
    dumped = yaml.dump(
        prepared,
        Dumper=_Dumper,
        sort_keys=False,
        allow_unicode=True,
        width=1000,
        default_flow_style=False,
    )
    normalized_body = body.replace("\r\n", "\n").replace("\r", "\n")
    return f"---\n{dumped}---\n{normalized_body}"
