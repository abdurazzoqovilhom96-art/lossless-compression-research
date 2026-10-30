#!/bin/bash
# Checks the frozen BDLC code inside bdlc-bench:2026-10-29.
#   /bdlc  BDLC project folder (read-only)
set -u
export PYTHONDONTWRITEBYTECODE=1 NUMBA_CACHE_DIR=/tmp/numba_cache
PY=/opt/bdlc-venv/bin/python
cd /bdlc || exit 1
echo "== freeze"
$PY tools/write_freeze.py --check
echo "== unit tests"
$PY -m unittest discover -s tests 2>&1 | tail -4
echo "== cpu"
nproc; grep -m1 "model name" /proc/cpuinfo
$PY -c "import os; print('affinity', sorted(os.sched_getaffinity(0))[:4], '... n =', len(os.sched_getaffinity(0)))"
