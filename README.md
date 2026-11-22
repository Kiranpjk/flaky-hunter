# flaky-hunter

[![CI](https://github.com/Kiranpjk/flaky-hunter/actions/workflows/ci.yml/badge.svg)](https://github.com/Kiranpjk/flaky-hunter/actions/workflows/ci.yml)
[![Docker](https://github.com/Kiranpjk/flaky-hunter/actions/workflows/docker.yml/badge.svg)](https://github.com/Kiranpjk/flaky-hunter/actions/workflows/docker.yml)

A dependency-free Python CLI (and GitHub Action) that reads the **JUnit XML reports from many
CI runs** and tells you which tests are flaky, which are simply broken, and which are stable.
It works with anything that writes JUnit XML: pytest, Jest (jest-junit), Playwright, Maven
Surefire, Gradle, Cypress.

## Problem

A test that passes and fails on the same code makes people stop trusting CI. They hit
"re-run" until it goes green, and real failures get lost in the noise. Most teams only notice
flakiness by feel, because each CI run is looked at on its own.

Source: r/RedditEng, <https://www.reddit.com/r/RedditEng/comments/1ap4axo/>. Reddit's iOS
team explains how flaky tests eroded trust in CI, forced costly re-runs and caused alert
fatigue, and how they built a service to detect and quarantine them automatically.
flaky-hunter is a small, self-hostable version of the detection half.

## How it decides

For every test it builds a chronological pass/fail history across runs (skips are ignored):

| Status | Rule |
| --- | --- |
| `stable` | never failed |
| `broken` | failed in every run: a real bug, not flakiness |
| `flaky` | both passed and failed |

Extra signals:

- **Same-commit evidence**: if a test passed *and* failed on the same commit, the code did
  not change but the result did. That is confirmed flakiness rather than a regression that
  was later fixed. The commit comes from a `<property name="commit">` in the report or from
  the file name via `--commit-regex`.
- **Flip rate**: the share of consecutive runs where the outcome changed.
- **Fail rate** and the last failure message.

## Architecture

```
reports/*.xml --parser.py (xml.etree)--> Run(commit, timestamp, [TestResult])
            --analysis.py--> TestStats per test (history, flip rate, same-commit flakes)
            --cli.py--> text | markdown | json, $GITHUB_STEP_SUMMARY, quarantine file, exit code
```

## Demo

`examples/demo_suite/test_checkout.py` contains two tests with typical flaky causes (a
timing-dependent "payment API" call and an ID collision from shared random state).
`examples/record_runs.sh` ran it 10 times with real pytest (`--junitxml`), pretending runs 1-5
were on commit `a1b2c3d` and 6-10 on `e4f5a6b`. Those reports are committed in
`examples/reports/`. Output from a local run:

```
$ flaky-hunter examples/reports --commit-regex 'run-([0-9a-f]{7,40})' --all
Analysed 10 runs, 5 tests.
test                                                        status  runs  fails  fail%  flip%  same-commit
examples.demo_suite.test_checkout::test_order_ids_unique    flaky     10      1    10%    22%  yes
examples.demo_suite.test_checkout::test_payment_timeout     flaky     10      2    20%    11%  yes
examples.demo_suite.test_checkout::test_cart_total          stable    10      0     0%     0%  -
examples.demo_suite.test_checkout::test_currency_format_de  stable    10      0     0%     0%  -
examples.demo_suite.test_checkout::test_empty_cart          stable    10      0     0%     0%  -

$ flaky-hunter examples/reports --max-flaky 1; echo "exit=$?"
...
2 flaky tests > allowed 1
exit=1
```

## Usage

```bash
pip install .            # no runtime dependencies
flaky-hunter path/to/reports [more.xml ...] \
  [--format text|markdown|json] [--all] \
  [--commit-regex 'run-([0-9a-f]{7,40})'] \
  [--max-flaky N] [--quarantine-file flaky.txt]
```

- `--max-flaky N`: exit code 1 when more than N tests are flaky (a CI gate).
- `--quarantine-file`: writes flaky test IDs, one per line, so you can skip or tag them.
- When `GITHUB_STEP_SUMMARY` is set, a markdown table is appended to the job summary.

### As a GitHub Action

Collect the JUnit artifacts from previous runs (for example with `actions/download-artifact`),
then:

```yaml
- uses: Kiranpjk/flaky-hunter@main
  with:
    reports: junit-reports/
    commit-regex: 'run-([0-9a-f]{7,40})'
    max-flaky: "0"
```

This repo's own CI runs the action against `examples/reports` (the `dogfood` job).

## Run with Docker

```bash
docker build -t flaky-hunter .
docker run --rm -v "$PWD/examples/reports:/reports:ro" flaky-hunter /reports --format markdown
```

Image published by CI: `ghcr.io/kiranpjk/flaky-hunter`.

## Tests

```bash
pip install -e ".[dev]"
pytest -q    # 9 tests: parsing (pytest + Jest-style nesting, <error>, <skipped>),
             # classification, same-commit logic, ordering, CLI formats, exit codes
```

## CI/CD

- `.github/workflows/ci.yml`: ruff + pytest on Python 3.11 to 3.13, plus a `dogfood` job that
  runs the composite action in `action.yml`.
- `.github/workflows/docker.yml`: builds on PRs; pushes to GHCR on `main` and `v*` tags with
  `GITHUB_TOKEN`.
- `.github/dependabot.yml`: weekly pip, Actions and Docker updates.

## Limitations

- Reports are parsed with the standard library `xml.etree`. Only feed it reports from your own CI.
- A test is identified by `classname::name`, so a renamed test starts a fresh history.

## License

MIT, see [LICENSE](LICENSE).
