"""Parse JUnit XML (pytest, Jest via jest-junit, Maven Surefire, Gradle, Playwright, ...)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

PASSED, FAILED, SKIPPED = "passed", "failed", "skipped"


@dataclass(frozen=True)
class TestResult:
    test_id: str
    outcome: str  # passed | failed | skipped
    duration: float
    message: str = ""


@dataclass
class Run:
    """One CI run = one report file (which may contain several <testsuite> elements)."""

    source: str
    timestamp: str
    commit: str | None
    results: list[TestResult]


def _outcome(case: ET.Element) -> tuple[str, str]:
    for tag in ("failure", "error"):
        node = case.find(tag)
        if node is not None:
            text = (node.get("message") or node.text or "").strip()
            return FAILED, text.splitlines()[0] if text else ""
    if case.find("skipped") is not None:
        return SKIPPED, ""
    return PASSED, ""


def parse_report(path: Path, commit_pattern: re.Pattern[str] | None = None) -> Run:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else root.findall(".//testsuite")
    results: list[TestResult] = []
    timestamp = ""
    commit = None

    for suite in suites:
        timestamp = timestamp or suite.get("timestamp", "")
        for prop in suite.findall("./properties/property"):
            if prop.get("name") in ("commit", "git_sha", "GITHUB_SHA"):
                commit = prop.get("value")
        for case in suite.iter("testcase"):
            cls = case.get("classname") or suite.get("name") or ""
            test_id = f"{cls}::{case.get('name', '?')}" if cls else case.get("name", "?")
            outcome, msg = _outcome(case)
            results.append(TestResult(test_id, outcome, float(case.get("time") or 0), msg[:200]))

    if commit is None and commit_pattern is not None:
        m = commit_pattern.search(path.name)
        commit = m.group(1) if m else None
    return Run(source=str(path), timestamp=timestamp, commit=commit, results=results)


def collect_reports(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for p in paths:
        files.extend(sorted(p.rglob("*.xml")) if p.is_dir() else [p])
    return files
