#!/bin/bash
# Preflight of all configurations (test A set + external CLI baselines) inside bdlc-bench:2026-10-29.
# Runs only the input audit and the synthetic-probe preflight (--write-protocol); no codec touches
# the inputs. /proj = project folder; protocol goes to /tmp and is summarised.
set -u
export PYTHONDONTWRITEBYTECODE=1 NUMBA_CACHE_DIR=/tmp/numba_cache
PY=/opt/bdlc-venv/bin/python
cd /proj/BDLC || exit 1
ALL=$($PY -c "import sys; sys.path[:0]=['bench']; import backends; print(','.join(backends.DEFAULT + backends.EXTERNAL))")
$PY bench/run_bench.py --manifest ../real_manifest.csv --split development --codecs "$ALL" \
    --write-protocol /tmp/protocol_preflight.json > /tmp/pf.log 2>&1 || { tail -20 /tmp/pf.log; exit 1; }
$PY - <<'EOF'
import json
p = json.load(open('/tmp/protocol_preflight.json'))
print('available:', len(p['codecs']), ' unavailable:', p['unavailable'] or 'none')
print('priority:', p['parameters']['priority'], '| cpu:', p['cpu'], '| platform:', p['platform'])
print('external tools hashed:', sorted(p.get('external_tools', {}).get('sha256', {})))
EOF
