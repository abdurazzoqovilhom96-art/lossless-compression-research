#!/bin/bash
# End-to-end harness check inside bdlc-bench:2026-10-29 on the development maps (a smoke run, not a
# result): pinning, coverage rule, null runs, verification, cold start and report.
#   docker run --cap-add SYS_NICE -v <project>:/proj bdlc-bench:2026-10-29 bash /proj/BDLC/docker/smoke_dev.sh
set -u
export PYTHONDONTWRITEBYTECODE=1 NUMBA_CACHE_DIR=/tmp/numba_cache
PY=/opt/bdlc-venv/bin/python
cd /proj/BDLC || exit 1
CODECS=bdlc,jpegls,crackle_mo0_zstd19,$($PY -c "import sys; sys.path[:0]=['bench']; import backends; print(','.join(backends.EXTERNAL))")
$PY bench/run_bench.py --manifest ../real_manifest.csv --split development --codecs "$CODECS" --repeats 3 \
    --out "runs/$(date +%Y%m%d_%H%M%S)_development_container_smoke"
