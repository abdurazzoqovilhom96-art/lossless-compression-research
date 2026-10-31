#!/bin/bash
# Runs the I/O calibration inside bdlc-bench:2026-10-29 (project mounted at /proj):
#   bash /proj/BDLC/posthoc/io_calibration/run_io.sh runs/<ts>_io_calibration
# Refuses to start if any file differs from the protocol written by prepare.py.
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1 NUMBA_CACHE_DIR=/tmp/numba_cache
PY=/opt/bdlc-venv/bin/python
cd /proj/BDLC
RUN="$1"
$PY - "$RUN" <<'EOF'
import hashlib, json, sys
run = sys.argv[1]
p = json.load(open(run + '/protocol_IO.json'))
bad = [f for f, h in p['code_sha256'].items() if hashlib.sha256(open(f, 'rb').read()).hexdigest() != h]
bad += [t for t, h in p['task_sha256'].items() if hashlib.sha256(open(run + '/tasks/' + t + '.json', 'rb').read()).hexdigest() != h]
if bad:
    sys.exit('protocol mismatch: %s' % bad)
print('protocol check OK')
EOF
# pass-through programs, executable copies inside the container
mkdir -p /tmp/io_shim
cp posthoc/io_calibration/bin/ecc_encoder posthoc/io_calibration/bin/ecc_decoder /tmp/io_shim/
chmod +x /tmp/io_shim/ecc_encoder /tmp/io_shim/ecc_decoder
for tag in ecc_real ecc_shim bdlc; do
    if [ "$tag" = ecc_shim ]; then BIN=/tmp/io_shim; else BIN=/opt/baselines/bin; fi
    echo "[$(date +%H:%M:%S)] $tag (BDLC_EXTERNAL_BIN=$BIN)"
    BDLC_EXTERNAL_BIN=$BIN $PY bench/worker.py "$RUN/tasks/$tag.json" > "$RUN/logs/$tag.txt" 2>&1
done
echo "[$(date +%H:%M:%S)] done"
$PY posthoc/io_calibration/analyze.py "$RUN"
