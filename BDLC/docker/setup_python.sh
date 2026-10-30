#!/bin/bash
# Adds the BDLC Python environment to bdlc-baselines:2026-10-29 (result is
# committed as bdlc-bench:2026-10-29).
#   /dl     downloads/python (read-only): python-build-standalone 3.14.4 tarball
#   /req    BDLC/requirements.txt (read-only): the pins used on Windows
#   /wheels downloads/wheels-cp314-linux: wheel cache (written once, then reused offline)
#   /out    docker/build_out
# Same Python version and the same package versions as the Windows runs.
set -euo pipefail
tar -xzf /dl/cpython-3.14.4+20260414-x86_64-unknown-linux-gnu-install_only.tar.gz -C /opt
/opt/python/bin/python3 -VV
if [ -z "$(ls -A /wheels)" ]; then
    /opt/python/bin/python3 -m pip download --disable-pip-version-check --only-binary=:all: \
        -r /req/requirements.txt -d /wheels
fi
/opt/python/bin/python3 -m venv /opt/bdlc-venv
/opt/bdlc-venv/bin/pip install --disable-pip-version-check --no-index --find-links /wheels -r /req/requirements.txt
/opt/bdlc-venv/bin/pip freeze --all > /out/pip_freeze_linux.txt
/opt/bdlc-venv/bin/python -VV > /out/python_linux.txt
( cd /wheels && sha256sum *.whl ) > /out/wheels.sha256
echo "wheels: $(ls /wheels | wc -l), $(du -sb /wheels | cut -f1) bytes"
