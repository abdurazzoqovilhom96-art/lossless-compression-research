"""Post-hoc I/O calibration of the command-line timing (paper limitation B1). Writes the run folder, the three
worker tasks and the protocol file BEFORE anything is timed.

    python -I posthoc/io_calibration/prepare.py

Design (fixed here, before the run):
  * Same machine, container image (bdlc-bench:2026-10-29), worker code, CPU core (2), priority (nice -10),
    repeats (3), warm-up and null-run subtraction as protocol B; the image list is the timing list of
    protocol B (1,169 maps; each task in the order its codec had in run B), taken from run 20261029_081034_test_B.
  * Three tasks, run one after another in one session:
      ecc_real : ecc_direct with the real ECC-2026 binaries (/opt/baselines/bin);
      ecc_shim : ecc_direct with pass-through programs that copy the input file to the output file, so the
                 harness performs every step of the ECC-2026 path except the coding itself;
      bdlc     : BDLC, for a same-session reference.
  * Analysis (posthoc/io_calibration/analyze.py), DAVIS 2017 timed maps, clusters = sequences:
      net time = median of the 3 repeats minus the median null (1x1) time of the same task;
      speed-up of BDLC over ECC-2026 as in B3 (geometric mean over sequences of summed times) and as the ratio
      of summed times, (a) for ecc_real as measured and (b) for ecc_real minus ecc_shim, i.e. with the file and
      conversion cost of the command-line path removed. Both are reported, whatever they show.
  * Nothing of protocol B is changed or re-used except the image list; run B's files are only read.
"""
import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BDLC = os.path.dirname(os.path.dirname(HERE))
RUNB = os.path.join(BDLC, 'runs', '20261029_081034_test_B')
CONT = '/proj/BDLC'                      # the project as mounted in the container


def sha(p):
    with open(p, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def main():
    src = {c: json.load(open(os.path.join(RUNB, 'tasks', c + '_bench.json'), encoding='utf-8'))
           for c in ('ecc_direct', 'bdlc')}
    # run B timed every codec on the same maps, each codec in its own random order; each task keeps its order
    assert sorted(i['input_id'] for i in src['ecc_direct']['images']) == sorted(i['input_id'] for i in src['bdlc']['images'])
    images = sorted(src['ecc_direct']['images'], key=lambda i: i['input_id'])
    ts = time.strftime('%Y%m%d_%H%M%S')
    name = ts + '_io_calibration'
    out = os.path.join(BDLC, 'runs', name)
    for d in ('tasks', 'raw', 'streams/ecc_real', 'streams/ecc_shim', 'streams/bdlc', 'logs'):
        os.makedirs(os.path.join(out, d), exist_ok=False)
    tasks = {}
    for tag, codec in (('ecc_real', 'ecc_direct'), ('ecc_shim', 'ecc_direct'), ('bdlc', 'bdlc')):
        t = dict(src[codec])
        t['output'] = '%s/runs/%s/raw/%s.json' % (CONT, name, tag)
        t['stream_dir'] = '%s/runs/%s/streams/%s' % (CONT, name, tag)
        assert t['repeats'] == 3 and t['cpu'] == 2 and t['high_priority'] is True and t['mode'] == 'bench'
        p = os.path.join(out, 'tasks', tag + '.json')
        with open(p, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(t, f, indent=1)
        tasks[tag] = p
    files = ['bench/worker.py', 'bench/backends.py', 'bench/external.py', 'bdlc/core.py', 'bdlc/api.py',
             'bdlc/__init__.py', 'bdlc/init_v1.npz', 'posthoc/io_calibration/bin/ecc_encoder',
             'posthoc/io_calibration/bin/ecc_decoder', 'posthoc/io_calibration/run_io.sh',
             'posthoc/io_calibration/analyze.py', 'posthoc/io_calibration/prepare.py']
    proto = {
        'purpose': 'post-hoc I/O calibration of the command-line timing (paper limitation B1)',
        'design': __doc__,
        'written_at_utc': time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime()),
        'run_folder': 'runs/' + name,
        'image_list_from': 'runs/20261029_081034_test_B/tasks/ecc_direct_bench.json',
        'image_list_sha256': hashlib.sha256(json.dumps([[i['input_id'], i['pixel_sha']] for i in images]).encode()).hexdigest(),
        'n_images': len(images),
        'code_sha256': {f: sha(os.path.join(BDLC, f)) for f in files},
        'task_sha256': {tag: sha(p) for tag, p in tasks.items()},
        'container_image': 'bdlc-bench:2026-10-29',
        'real_ecc_binaries': '/opt/baselines/bin (hashes recorded in protocol_B.json)',
    }
    p = os.path.join(out, 'protocol_IO.json')
    with open(p, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(proto, f, indent=1)
    print('run folder:', 'runs/' + name)
    print('protocol_IO.json sha256:', sha(p))


if __name__ == '__main__':
    sys.exit(main())
