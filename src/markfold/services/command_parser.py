from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ParsedCommand:
    name: str
    args: dict[str, str] = field(default_factory=dict)


def parse_command(raw_text: str) -> ParsedCommand | None:
    text = raw_text.strip()
    if not text:
        return None

    if text.startswith("#new"):
        title = text.removeprefix("#new").strip()
        return ParsedCommand(name="init", args={"title": title})

    if not text.startswith("/"):
        return None

    first_line, _, rest = text.partition("\n")
    parts = first_line.split(maxsplit=1)
    command = parts[0].removeprefix("/")
    inline_arg = parts[1].strip() if len(parts) > 1 else ""

    if command == "init":
        args: dict[str, str] = {}
        payload = rest.strip()
        if payload and ":" in payload:
            for line in payload.splitlines():
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                args[key.strip()] = value.strip()
        elif inline_arg:
            args["title"] = inline_arg
        return ParsedCommand(name="init", args=args)

    if command in {"use", "todo", "done", "status"}:
        value = inline_arg or rest.strip()
        return ParsedCommand(name=command, args={"value": value})

    if command in {"finish-init", "cancel-init"}:
        return ParsedCommand(name=command)

    return None
