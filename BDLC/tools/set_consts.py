"""Development helper: set module-level integer constants in bdlc/core.py (e.g. PMAX=2 REL_CTX=1)."""
import os
import re
import sys

path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'bdlc', 'core.py')
src = open(path, encoding='utf-8').read()
for arg in sys.argv[1:]:
    k, v = arg.split('=')
    src, n = re.subn(r'^(%s = )(-?\d+)' % re.escape(k), r'\g<1>' + v, src, count=1, flags=re.M)
    if n != 1:
        raise SystemExit('constant not found: ' + k)
open(path, 'w', encoding='utf-8', newline='').write(src)
print('set', ' '.join(sys.argv[1:]))
