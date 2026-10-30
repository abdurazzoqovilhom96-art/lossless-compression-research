#!/bin/bash
# Smoke test of the two-phase harness (parallel size phase + pinned timing phase) on development maps.
set -u
export PYTHONDONTWRITEBYTECODE=1 NUMBA_CACHE_DIR=/tmp/numba_cache
cd /proj/BDLC || exit 1
/opt/bdlc-venv/bin/python bench/run_bench.py --manifest docker/manifest_dev_twophase.csv --split development \
    --codecs bdlc,jpegls,crackle_mo0_zstd19,ecc_direct,flif_pi_e60,compresso,hevc_scc_direct --repeats 3 \
    --size-jobs 8 --shard-size 10 --timing-column timing --skip-tests \
    --out "runs/$(date +%Y%m%d_%H%M%S)_development_twophase_smoke"
