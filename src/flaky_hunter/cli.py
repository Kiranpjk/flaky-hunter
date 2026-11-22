"""flaky-hunter: compare JUnit XML reports from many CI runs and list flaky tests."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from .analysis import BROKEN, FLAKY, TestStats, analyse
from .parser import collect_reports, parse_report


def render_text(stats: list[TestStats], runs: int, show_all: bool) -> str:
    rows = [s for s in stats if show_all or s.status != "stable"]
    out = [f"Analysed {runs} runs, {len(stats)} tests."]
    if not rows:
        return "\n".join(out + ["No flaky or broken tests found."])
    width = max(len(s.test_id) for s in rows)
    out.append(f"{'test'.ljust(width)}  status  runs  fails  fail%  flip%  same-commit")
    for s in rows:
        out.append(
            f"{s.test_id.ljust(width)}  {s.status:<6}  {s.runs:>4}  {s.failures:>5}  "
            f"{s.fail_rate:>5.0%}  {s.flip_rate:>5.0%}  {'yes' if s.confirmed else '-'}"
        )
    return "\n".join(out)


def render_markdown(stats: list[TestStats], runs: int) -> str:
    flaky = [s for s in stats if s.status in (FLAKY, BROKEN)]
    lines = [f"### flaky-hunter: {runs} runs, {len(stats)} tests", ""]
    if not flaky:
        return "\n".join(lines + ["No flaky or broken tests found."])
    lines += [
        "| Test | Status | Fail rate | Flip rate | Same-commit evidence | Last failure |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for s in flaky:
        msg = s.last_failure.replace("|", "\\|")[:80]
        lines.append(
            f"| `{s.test_id}` | {s.status} | {s.fail_rate:.0%} | {s.flip_rate:.0%} | "
            f"{'yes' if s.confirmed else 'no'} | {msg} |"
        )
    return "\n".join(lines)


def render_json(stats: list[TestStats], runs: int) -> str:
    return json.dumps(
        {
            "runs": runs,
            "tests": [
                {
                    "id": s.test_id,
                    "status": s.status,
                    "runs": s.runs,
                    "failures": s.failures,
                    "fail_rate": round(s.fail_rate, 3),
                    "flip_rate": round(s.flip_rate, 3),
                    "flaky_commits": sorted(s.flaky_commits),
                    "last_failure": s.last_failure,
                }
                for s in stats
            ],
        },
        indent=2,
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="flaky-hunter", description=__doc__)
    p.add_argument("reports", nargs="+", type=Path, help="JUnit XML files or directories")
    p.add_argument("--format", choices=["text", "markdown", "json"], default="text")
    p.add_argument("--all", action="store_true", help="also list stable tests (text format)")
    p.add_argument(
        "--commit-regex",
        help="regex with one group that extracts the commit SHA from the file name, "
        r"e.g. 'run-([0-9a-f]{7,40})'",
    )
    p.add_argument(
        "--max-flaky",
        type=int,
        default=None,
        help="exit with code 1 if more than this many tests are flaky",
    )
    p.add_argument("--quarantine-file", type=Path, help="write flaky test IDs, one per line")
    args = p.parse_args(argv)

    files = collect_reports(args.reports)
    if not files:
        print("no JUnit XML reports found", file=sys.stderr)
        return 2
    pattern = re.compile(args.commit_regex) if args.commit_regex else None
    runs = [parse_report(f, pattern) for f in files]
    stats = analyse(runs)

    if args.format == "markdown":
        report = render_markdown(stats, len(runs))
    elif args.format == "json":
        report = render_json(stats, len(runs))
    else:
        report = render_text(stats, len(runs), args.all)
    print(report)

    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(render_markdown(stats, len(runs)) + "\n")

    flaky = [s for s in stats if s.status == FLAKY]
    if args.quarantine_file:
        args.quarantine_file.write_text("".join(f"{s.test_id}\n" for s in flaky), "utf-8")
    if args.max_flaky is not None and len(flaky) > args.max_flaky:
        print(f"\n{len(flaky)} flaky tests > allowed {args.max_flaky}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
