#!/bin/bash
# Test cohort C (PROTOKOL_C_UZ.md): COCO-Stuff val2017 semantic maps. Inside bdlc-bench:2026-10-29,
# project mounted at /proj. Same harness, configurations and parameters as protocol B.
#   bash run_C.sh write   -> writes protocol_C.json (no codec touches the inputs)
#   bash run_C.sh run     -> the single run; refuses to start if anything differs from protocol_C.json
set -u
export PYTHONDONTWRITEBYTECODE=1 NUMBA_CACHE_DIR=/tmp/numba_cache
PY=/opt/bdlc-venv/bin/python
cd /proj/BDLC || exit 1
CODECS=$($PY -c "import sys; sys.path[:0]=['bench']; import backends; print(','.join(backends.DEFAULT + backends.EXTERNAL))")
# size phase: all 5,000 maps, 20 parallel workers; timing phase: the 1,000 maps with timing=1, one pinned
# vCPU, one codec at a time, nothing else running
COMMON=(--manifest manifest_C.csv --split test --codecs "$CODECS" --repeats 3 --exclude-manifest ../real_manifest.csv
        --size-jobs 20 --shard-size 100 --timing-column timing)
case "${1:-}" in
    write) exec $PY bench/run_bench.py "${COMMON[@]}" --write-protocol protocol_C.json ;;
    run)   exec $PY bench/run_bench.py "${COMMON[@]}" --protocol protocol_C.json --timeout 43200 \
               --out "runs/$(date +%Y%m%d_%H%M%S)_test_C" ;;
    *)     echo "usage: run_C.sh write|run"; exit 2 ;;
esac
