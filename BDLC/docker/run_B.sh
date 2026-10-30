#!/bin/bash
# Test cohort B (PROTOKOL_B_UZ.md). Inside bdlc-bench:2026-10-29, project mounted at /proj.
#   bash run_B.sh write   -> writes protocol_B.json (no codec touches the inputs)
#   bash run_B.sh run     -> the single run; refuses to start if anything differs from protocol_B.json
set -u
export PYTHONDONTWRITEBYTECODE=1 NUMBA_CACHE_DIR=/tmp/numba_cache
PY=/opt/bdlc-venv/bin/python
cd /proj/BDLC || exit 1
CODECS=$($PY -c "import sys; sys.path[:0]=['bench']; import backends; print(','.join(backends.DEFAULT + backends.EXTERNAL))")
# size phase: all 6477 maps, 20 parallel workers (sizes are deterministic, so parallelism cannot change them);
# timing phase: the 1169 maps with timing=1, one pinned vCPU, one codec at a time, nothing else running
COMMON=(--manifest manifest_B.csv --split test --codecs "$CODECS" --repeats 3 --exclude-manifest ../real_manifest.csv
        --size-jobs 20 --shard-size 100 --timing-column timing)
case "${1:-}" in
    write) exec $PY bench/run_bench.py "${COMMON[@]}" --write-protocol protocol_B.json ;;
    run)   exec $PY bench/run_bench.py "${COMMON[@]}" --protocol protocol_B.json --timeout 43200 \
               --out "runs/$(date +%Y%m%d_%H%M%S)_test_B" ;;
    *)     echo "usage: run_B.sh write|run"; exit 2 ;;
esac
