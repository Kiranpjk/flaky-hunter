import json
import re
from pathlib import Path

import pytest

from flaky_hunter.analysis import BROKEN, FLAKY, STABLE, analyse
from flaky_hunter.cli import main
from flaky_hunter.parser import FAILED, PASSED, SKIPPED, parse_report

EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "reports"


def write(tmp_path: Path, name: str, cases: dict[str, str], ts: str, commit: str | None = None):
    """cases: test name -> 'pass' | 'fail' | 'error' | 'skip'."""
    body = {
        "pass": "",
        "fail": '<failure message="boom">trace</failure>',
        "error": "<error>conn refused\nmore</error>",
        "skip": "<skipped/>",
    }
    props = f'<properties><property name="commit" value="{commit}"/></properties>' if commit else ""
    xml = (
        f'<testsuite name="suite" timestamp="{ts}">{props}'
        + "".join(
            f'<testcase classname="pkg.T" name="{n}" time="0.1">{body[o]}</testcase>'
            for n, o in cases.items()
        )
        + "</testsuite>"
    )
    path = tmp_path / name
    path.write_text(xml)
    return path


def test_parse_outcomes_and_commit_property(tmp_path):
    p = write(tmp_path, "r.xml", {"a": "pass", "b": "fail", "c": "error", "d": "skip"}, "t1", "abc")
    run = parse_report(p)
    assert run.commit == "abc"
    outcomes = {r.test_id: (r.outcome, r.message) for r in run.results}
    assert outcomes == {
        "pkg.T::a": (PASSED, ""),
        "pkg.T::b": (FAILED, "boom"),
        "pkg.T::c": (FAILED, "conn refused"),
        "pkg.T::d": (SKIPPED, ""),
    }


def test_parse_nested_testsuites_jest_style(tmp_path):
    p = tmp_path / "jest-deadbeef.xml"
    p.write_text(
        '<testsuites name="jest tests"><testsuite name="Cart" timestamp="2026-01-01T10:00:00">'
        '<testcase classname="Cart adds item" name="Cart adds item" time="0.01"/>'
        "</testsuite></testsuites>"
    )
    run = parse_report(p, re.compile(r"jest-([0-9a-f]+)"))
    assert run.commit == "deadbeef"
    assert [r.test_id for r in run.results] == ["Cart adds item::Cart adds item"]


def test_classification(tmp_path):
    runs = [
        parse_report(write(tmp_path, f"{i}.xml", cases, f"t{i}", "c1"))
        for i, cases in enumerate(
            [
                {"stable": "pass", "flaky": "pass", "broken": "fail", "skipped": "skip"},
                {"stable": "pass", "flaky": "fail", "broken": "error", "skipped": "skip"},
                {"stable": "pass", "flaky": "pass", "broken": "fail", "skipped": "skip"},
            ]
        )
    ]
    by_id = {s.test_id.split("::")[1]: s for s in analyse(runs)}
    assert by_id["stable"].status == STABLE
    assert by_id["broken"].status == BROKEN
    assert by_id["flaky"].status == FLAKY
    assert by_id["flaky"].confirmed and by_id["flaky"].flaky_commits == {"c1"}
    assert by_id["flaky"].flip_rate == 1.0
    assert "skipped" not in by_id  # skips are not evidence either way


def test_failures_on_different_commits_are_not_confirmed(tmp_path):
    runs = [
        parse_report(write(tmp_path, "1.xml", {"x": "pass"}, "t1", "old")),
        parse_report(write(tmp_path, "2.xml", {"x": "fail"}, "t2", "new")),
    ]
    (st,) = analyse(runs)
    assert st.status == FLAKY and not st.confirmed  # may just be a regression


def test_runs_sorted_by_timestamp(tmp_path):
    runs = [
        parse_report(write(tmp_path, "a.xml", {"x": "fail"}, "2026-01-02")),
        parse_report(write(tmp_path, "b.xml", {"x": "pass"}, "2026-01-01")),
    ]
    assert analyse(runs)[0].history == [PASSED, FAILED]


def test_cli_on_recorded_pytest_reports(capsys, tmp_path):
    q = tmp_path / "quarantine.txt"
    args = [str(EXAMPLES), "--commit-regex", r"run-([0-9a-f]{7})", "--quarantine-file", str(q)]
    assert main(args + ["--max-flaky", "5"]) == 0
    out = capsys.readouterr().out
    assert "Analysed 10 runs, 5 tests." in out
    assert set(q.read_text().split()) == {
        "examples.demo_suite.test_checkout::test_payment_timeout",
        "examples.demo_suite.test_checkout::test_order_ids_unique",
    }
    assert main(args + ["--max-flaky", "1"]) == 1


@pytest.mark.parametrize("fmt", ["markdown", "json"])
def test_output_formats_and_step_summary(fmt, capsys, tmp_path, monkeypatch):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert main([str(EXAMPLES), "--format", fmt]) == 0
    out = capsys.readouterr().out
    if fmt == "json":
        data = json.loads(out)
        assert data["runs"] == 10 and len(data["tests"]) == 5
    else:
        assert "| `examples.demo_suite.test_checkout::test_payment_timeout` | flaky" in out
    assert "flaky-hunter: 10 runs" in summary.read_text()


def test_no_reports(tmp_path):
    assert main([str(tmp_path)]) == 2
