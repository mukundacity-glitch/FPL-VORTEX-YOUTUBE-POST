"""Regenerate the Day 3 ``player_out_*`` dropdowns from the live FPL squad.

GitHub ``workflow_dispatch`` ``choice`` options are static YAML: they cannot
call an API when the dispatch form opens. The only way to make them automatic is
to rewrite them from the official FPL API on a schedule. This script does that
for all five OUT inputs, deterministically, so a scheduled run produces no diff
while the manager's 15 players are unchanged.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Sequence

from day3.fpl_squad import LiveSquad, LiveSquadError, resolve_live_squad

PLAYER_OUT_INPUT_RE = re.compile(r"^      player_out_([1-5]):\s*$")
OPTIONS_HEADER_RE = re.compile(r"^        options:\s*$")
OPTION_LINE_RE = re.compile(r'^          - "(?:[^"\\]|\\.)*"\s*$')
GENERATED_COMMENT = (
    "          # Generated from the official FPL API by day3/refresh_day3_choices.py"
)


def quote_choice(value: str) -> str:
    """JSON quoting is valid YAML double-quoted-scalar quoting."""
    return json.dumps(str(value), ensure_ascii=False)


def replace_out_options(workflow_text: str, choices: Sequence[str]) -> str:
    """Replace all five OUT option lists with ``NONE`` + the live 15."""
    if len(choices) != 15 or len(set(choices)) != 15:
        raise LiveSquadError("Exactly 15 unique live squad choices are required")
    lines = workflow_text.splitlines(keepends=True)
    output: list[str] = []
    index = 0
    replaced: set[str] = set()
    while index < len(lines):
        line = lines[index]
        match = PLAYER_OUT_INPUT_RE.match(line.rstrip("\r\n"))
        if not match:
            output.append(line)
            index += 1
            continue
        input_name = match.group(1)
        if input_name in replaced:
            raise LiveSquadError(f"Duplicate player_out_{input_name} input block")
        replaced.add(input_name)

        header = [line]
        index += 1
        while index < len(lines) and not OPTIONS_HEADER_RE.match(
            lines[index].rstrip("\r\n")
        ):
            header.append(lines[index])
            index += 1
        if index >= len(lines):
            raise LiveSquadError(f"player_out_{input_name} has no options: block")
        header.append(lines[index])  # the `options:` line itself
        index += 1

        # Drop any previous generated marker/blank lines; exactly one is emitted.
        while index < len(lines) and (
            not lines[index].strip() or lines[index].lstrip().startswith("#")
        ):
            index += 1
        option_count = 0
        while index < len(lines) and OPTION_LINE_RE.match(lines[index].rstrip("\r\n")):
            option_count += 1
            index += 1
        if option_count == 0:
            raise LiveSquadError(f"player_out_{input_name} has no option lines")

        output.extend(header)
        output.append(GENERATED_COMMENT + "\n")
        for choice in ("NONE", *choices):
            output.append(f"          - {quote_choice(choice)}\n")

    if replaced != {"1", "2", "3", "4", "5"}:
        raise LiveSquadError(
            "Expected five player_out_1..5 choice inputs, found "
            + (", ".join(sorted(replaced)) or "none")
        )
    return "".join(output)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Refresh Day 3 OUT dropdowns from the official FPL API."
    )
    parser.add_argument(
        "--entry-id",
        type=int,
        default=int(os.environ.get("FPL_ENTRY_ID", "145784")),
    )
    parser.add_argument(
        "--workflow",
        type=Path,
        default=Path(".github/workflows/day-3.yml"),
    )
    parser.add_argument(
        "--squad-json",
        type=Path,
        default=None,
        help="Reuse a previously resolved live squad snapshot (offline/testing).",
    )
    parser.add_argument("--summary", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if args.squad_json is not None:
        squad = LiveSquad.from_dict(json.loads(args.squad_json.read_text(encoding="utf-8")))
    else:
        squad = resolve_live_squad(args.entry_id)

    original = args.workflow.read_text(encoding="utf-8")
    updated = replace_out_options(original, squad.choices)
    changed = updated != original
    print(
        f"Day 3 OUT choices: entry {squad.entry_id}, GW{squad.base_gw}, "
        f"digest {squad.digest}, changed={changed}"
    )
    for choice in squad.choices:
        print(f"  {choice}")
    if changed and not args.dry_run:
        args.workflow.write_text(updated, encoding="utf-8")
        print(f"Updated {args.workflow}")
    if args.summary is not None:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        summary = [
            f"## Day 3 Player OUT choices (FPL entry {squad.entry_id})",
            "",
            f"Live squad: GW{squad.base_gw} (planning GW{squad.planning_gw}), "
            f"digest `{squad.digest}`.",
            "",
            "```text",
            *squad.choices,
            "```",
            "",
            "Workflow updated." if changed else "Workflow already up to date.",
            "",
        ]
        with args.summary.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(summary))
    return 0


if __name__ == "__main__":  # pragma: no cover
    try:
        sys.exit(main())
    except (LiveSquadError, OSError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
