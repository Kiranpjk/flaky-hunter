"""Classify tests across runs: stable, flaky, broken."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .parser import FAILED, PASSED, Run

STABLE, FLAKY, BROKEN = "stable", "flaky", "broken"


@dataclass
class TestStats:
    test_id: str
    history: list[str] = field(default_factory=list)  # chronological pass/fail, skips dropped
    flaky_commits: set[str] = field(default_factory=set)
    last_failure: str = ""
    total_time: float = 0.0

    @property
    def runs(self) -> int:
        return len(self.history)

    @property
    def failures(self) -> int:
        return self.history.count(FAILED)

    @property
    def fail_rate(self) -> float:
        return self.failures / self.runs if self.runs else 0.0

    @property
    def flip_rate(self) -> float:
        """Share of consecutive runs where the outcome changed. 1.0 = alternates every run."""
        if self.runs < 2:
            return 0.0
        flips = sum(1 for a, b in zip(self.history, self.history[1:], strict=False) if a != b)
        return flips / (self.runs - 1)

    @property
    def status(self) -> str:
        if self.failures == 0:
            return STABLE
        if self.failures == self.runs:
            return BROKEN
        return FLAKY

    @property
    def confirmed(self) -> bool:
        """Passed and failed on the same commit: the code did not change, the result did."""
        return bool(self.flaky_commits)


def analyse(runs: list[Run]) -> list[TestStats]:
    runs = sorted(runs, key=lambda r: (r.timestamp, r.source))
    stats: dict[str, TestStats] = {}
    per_commit: dict[tuple[str, str], set[str]] = defaultdict(set)

    for run in runs:
        for res in run.results:
            if res.outcome not in (PASSED, FAILED):
                continue
            st = stats.setdefault(res.test_id, TestStats(res.test_id))
            st.history.append(res.outcome)
            st.total_time += res.duration
            if res.outcome == FAILED:
                st.last_failure = res.message or st.last_failure
            if run.commit:
                per_commit[(res.test_id, run.commit)].add(res.outcome)

    for (test_id, commit), outcomes in per_commit.items():
        if outcomes == {PASSED, FAILED}:
            stats[test_id].flaky_commits.add(commit)

    order = {FLAKY: 0, BROKEN: 1, STABLE: 2}
    return sorted(stats.values(), key=lambda s: (order[s.status], -s.flip_rate, s.test_id))
