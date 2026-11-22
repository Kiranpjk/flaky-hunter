#!/usr/bin/env bash
# Record 10 JUnit reports from the demo suite: runs 1-5 "on" commit a1b2c3d, 6-10 on e4f5a6b.
set -euo pipefail
cd "$(dirname "$0")"
rm -rf reports && mkdir reports
for i in $(seq 1 10); do
  sha=$([ "$i" -le 5 ] && echo a1b2c3d || echo e4f5a6b)
  DEMO_SEED=$i python -m pytest demo_suite -q -p no:cacheprovider \
    --junitxml="reports/run-${sha}-$(printf %02d "$i").xml" >/dev/null || true
done
ls reports
