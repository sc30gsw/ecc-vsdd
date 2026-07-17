#!/usr/bin/env python3
"""Enforce line-only coverage without conflating it with branch coverage."""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("coverage_json", type=Path)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--minimum", type=Decimal, default=Decimal("80"))
    args = parser.parse_args()

    data = json.loads(args.coverage_json.read_text(encoding="utf-8"))
    files = data.get("files", {})
    failed = False
    total_covered = 0
    total_statements = 0
    for requested in args.paths:
        requested_resolved = requested.resolve()
        matches = [
            (name, value)
            for name, value in files.items()
            if Path(name).resolve() == requested_resolved
        ]
        if len(matches) != 1:
            print(f"coverage entry is missing or ambiguous: {requested}", file=sys.stderr)
            failed = True
            continue
        _, record = matches[0]
        summary = record.get("summary", {})
        covered = int(summary.get("covered_lines", 0))
        statements = int(summary.get("num_statements", 0))
        percent = (
            Decimal(covered) * Decimal(100) / Decimal(statements)
            if statements
            else Decimal(100)
        )
        print(f"{requested}: {percent:.1f}% ({covered}/{statements} lines)")
        total_covered += covered
        total_statements += statements
        if percent < args.minimum:
            failed = True

    overall = (
        Decimal(total_covered) * Decimal(100) / Decimal(total_statements)
        if total_statements
        else Decimal(0)
    )
    print(f"selected scripts: {overall:.1f}% ({total_covered}/{total_statements} lines)")
    if overall < args.minimum:
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
