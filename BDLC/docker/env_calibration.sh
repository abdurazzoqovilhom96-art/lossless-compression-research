#!/bin/bash
# Two rounds of env_calibration.py over a few codecs, one process per codec.
#   /proj  project folder (read-only; development maps + real_manifest.csv)
#   /out   docker/build_out
set -u
export PYTHONDONTWRITEBYTECODE=1 NUMBA_CACHE_DIR=/tmp/numba_cache
PY=/opt/bdlc-venv/bin/python
# fill the Numba cache once so that JIT compilation is not timed
$PY -c "import sys; sys.path[:0]=['/proj/BDLC']; import numpy as np, bdlc; a=np.zeros((8,8),np.uint16); a[2:5,3:6]=7; assert (bdlc.decode(bdlc.encode(a))==a).all()"
for round in 1 2; do
    for c in bdlc jpegls zstd3 zstd19 crackle_mo0_zstd19 jpegxl7; do
        $PY /proj/BDLC/docker/env_calibration.py "$c" /proj/real_manifest.csv /out/env_calibration_round$round.csv 2 9 \
            | tail -1 | cut -c1-140
    done
done
