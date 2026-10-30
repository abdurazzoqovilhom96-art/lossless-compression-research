"""Tables, comparisons, statistics and figures from one benchmark run directory.

Formulas (B = stream bytes, N = pixels, t = median of the timed repeats of one image):
  bpp_i = 8 B_i / N_i;  micro bpp = 8 sum B / sum N;  macro bpp = mean_i bpp_i;  CR = 16 / micro bpp
  size_gain %        = 100 (1 - sum B_ours / sum B_ref)            over the images both codecs completed
  encode/decode speedup = sum t_ref / sum t_ours;  time_reduction % = 100 (1 - sum t_ours / sum t_ref)
  throughput MPix/s  = sum N / sum t / 1e6
  joint win (image)  = B_ours < B_ref and t_enc,ours < t_enc,ref; decode wins are reported separately.
Only images that were measured AND independently verified are used.  A summary row with less than
full coverage is flagged and never used to name a winner.
Usage: python bench/report.py RUN_DIR
"""
import csv
import json
import math
import os
import sys

import numpy as np

BENCH = os.path.dirname(os.path.abspath(__file__))
if BENCH not in sys.path:
    sys.path.insert(0, BENCH)
import backends  # noqa: E402

OURS = 'bdlc'
POOLED = 'ALL_REAL'     # all non-synthetic datasets pooled
KEY_REFS = ['jpegxl10', 'jpegxl9', 'jpegxl7', 'crackle_mo3_zstd19', 'crackle_mo0_zstd19', 'crackle_mo3',
            'palette_lzma9e', 'lzma9e', 'zstd19', 'jpegls', 'zstd3', 'lerc_zstd', 'cseg_gzip9', 'png16', 'rvc']
INK, INK2, MUTED, GRID, AXIS, SURF = '#0b0b0b', '#52514e', '#898781', '#e1e0d9', '#c3c2b7', '#fcfcfb'
HL, OTHER = '#2a78d6', '#b9b7ae'                 # highlight (BDLC) / everything else
DS_COLORS = ['#2a78d6', '#eb6834', '#1baf7a']    # categorical slots 1-3 (validated all-pairs, light)


def jload(p):
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def csvout(path, rows, fields=None):
    if not rows:
        return
    fields = fields or list(rows[0])
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


def short(ds):
    return ds.replace('_GT_SEG', '')


def fmt(v, nd=4):
    if v is None or v == '':
        return ''
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    return ('%.' + str(nd) + 'f') % v


# ------------------------------------------------------------------ statistics helpers
def sign_test(wins, n):
    """One-sided P[X >= wins], X ~ Bin(n, 1/2); two-sided = min(1, 2 * min tail)."""
    if n == 0:
        return None, None
    pmf = [math.comb(n, k) / 2 ** n for k in range(n + 1)]
    upper = sum(pmf[wins:])
    lower = sum(pmf[:wins + 1])
    return upper, min(1.0, 2 * min(upper, lower))


def wilcoxon_exact(d):
    """Exact one-sided Wilcoxon signed-rank test that the d_i are shifted below 0.
    Zeros dropped; tied |d| get average ranks (handled exactly by doubling ranks).
    Returns (n_used, W_plus, p_one_sided)."""
    d = np.asarray([x for x in d if x != 0], float)
    n = len(d)
    if n == 0:
        return 0, None, None
    order = np.argsort(np.abs(d), kind='mergesort')
    ranks = np.empty(n)
    a = np.abs(d)[order]
    i = 0
    while i < n:
        j = i
        while j + 1 < n and a[j + 1] == a[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j + 2) / 2.0
        i = j + 1
    r2 = np.rint(2 * ranks).astype(int)
    wplus2 = int(r2[d > 0].sum())
    dist = {0: 1}
    for r in r2:
        nd = dict(dist)
        for s, c in dist.items():
            nd[s + r] = nd.get(s + r, 0) + c
        dist = nd
    p = sum(c for s, c in dist.items() if s <= wplus2) / 2 ** n
    return n, wplus2 / 2.0, p


def cluster_bootstrap(totals, reps=10000, seed=20261028):
    """95% percentile CI of size gain over resampled groups; totals = [[B_ours, B_ref], ...]."""
    v = np.asarray(totals, float)
    if len(v) < 6:
        return None, None
    rng = np.random.default_rng(seed)
    s = v[rng.integers(0, len(v), (reps, len(v)))].sum(axis=1)
    g = 100 * (1 - s[:, 0] / s[:, 1])
    lo, hi = np.percentile(g, [2.5, 97.5])
    return float(lo), float(hi)


# ------------------------------------------------------------------ build
def build(root):
    root = os.path.abspath(root)
    status = jload(os.path.join(root, 'status.json'))
    audit = {r['input_id']: r for r in jload(os.path.join(root, 'provenance', 'input_audit.json'))}
    ds_images = {}
    for r in audit.values():
        ds_images.setdefault(r['dataset'], set()).add(r['input_id'])

    per = []
    for c in status['codecs']:
        rp, vp = os.path.join(root, 'raw', c + '.json'), os.path.join(root, 'verification', c + '.json')
        if not (os.path.exists(rp) and os.path.exists(vp)):
            continue
        ver = {v['input_id']: v for v in jload(vp)['images']}
        raw = jload(rp)
        # command-line codecs: subtract the median null (1x1) call, Q1_REJA_UZ.md §1.6
        cli = backends.SPEC[c][1] == 'cli'
        null = raw.get('null', {})
        ne = null.get('enc_median_ns', 0) / 1e9 if cli else 0.0
        nd = null.get('dec_median_ns', 0) / 1e9 if cli else 0.0
        for m in raw['images']:
            v = ver.get(m['input_id'])
            if not v or not v['ok'] or v.get('stream_sha256') != m['stream_sha256']:
                continue
            a = audit[m['input_id']]
            n = a['pixels']
            te_raw, td_raw = m['enc_median_ns'] / 1e9, m['dec_median_ns'] / 1e9
            te, td = max(te_raw - ne, 1e-9), max(td_raw - nd, 1e-9)
            per.append({'input_id': m['input_id'], 'dataset': a['dataset'], 'group': a['group'], 'codec': c,
                        'family': backends.SPEC[c][0], 'pixels': n, 'K': a['K'], 'bytes': m['bytes'],
                        'stream_bytes': m.get('stream_bytes', m['bytes']),
                        'bpp': 8 * m['bytes'] / n, 'encode_s': te, 'decode_s': td,
                        'encode_MPix_s': n / te / 1e6, 'decode_MPix_s': n / td / 1e6,
                        'encode_s_raw': te_raw, 'decode_s_raw': td_raw, 'null_encode_s': ne, 'null_decode_s': nd,
                        'deterministic': m['deterministic'], 'verified': True})
    per.sort(key=lambda r: (r['dataset'], r['input_id'], r['codec']))
    os.makedirs(os.path.join(root, 'tables'), exist_ok=True)
    csvout(os.path.join(root, 'tables', 'per_image.csv'), per)
    csvout(os.path.join(root, 'plot_data', 'per_image.csv'), per)

    # size-only LOSO pseudo-codec (development): same images, honest development sizes
    loso = {}
    lp = os.path.join(root, 'tables', 'loso_sizes.csv')
    if os.path.exists(lp):
        with open(lp, encoding='utf-8') as f:
            loso = {r['input_id']: int(r['bytes_loso']) for r in csv.DictReader(f)}

    # pooled scope: real datasets only (a manifest column synthetic=true keeps simulated data apart)
    members = dict(ds_images)
    members[POOLED] = {i for i, r in audit.items() if str(r.get('synthetic', 'false')).lower() != 'true'}
    scopes = sorted(ds_images) + [POOLED]

    def rows_in(scope, codec):
        return [r for r in per if r['codec'] == codec and r['input_id'] in members[scope]]

    def n_images(scope):
        return len(members[scope])

    # ---- summary
    summary = []
    for s in scopes:
        for c in status['codecs']:
            rs = rows_in(s, c)
            if not rs:
                continue
            N = sum(r['pixels'] for r in rs)
            B = sum(r['bytes'] for r in rs)
            te, td = sum(r['encode_s'] for r in rs), sum(r['decode_s'] for r in rs)
            micro = 8 * B / N
            summary.append({'dataset': s, 'codec': c, 'family': backends.SPEC[c][0], 'images': len(rs),
                            'dataset_images': n_images(s), 'full_coverage': len(rs) == n_images(s),
                            'total_bytes': B, 'total_pixels': N, 'micro_bpp': micro,
                            'macro_bpp': float(np.mean([r['bpp'] for r in rs])), 'CR': 16 / micro,
                            'encode_s_sum': te, 'decode_s_sum': td,
                            'encode_MPix_s': N / te / 1e6, 'decode_MPix_s': N / td / 1e6})
        if loso:
            ids = [i for i in loso if i in members[s]]
            if ids:
                N = sum(audit[i]['pixels'] for i in ids)
                B = sum(loso[i] for i in ids)
                summary.append({'dataset': s, 'codec': 'bdlc_loso (size only)', 'family': 'BDLC', 'images': len(ids),
                                'dataset_images': n_images(s), 'full_coverage': len(ids) == n_images(s),
                                'total_bytes': B, 'total_pixels': N, 'micro_bpp': 8 * B / N,
                                'macro_bpp': float(np.mean([8 * loso[i] / audit[i]['pixels'] for i in ids])),
                                'CR': 16 / (8 * B / N), 'encode_s_sum': '', 'decode_s_sum': '',
                                'encode_MPix_s': '', 'decode_MPix_s': ''})
    csvout(os.path.join(root, 'tables', 'summary.csv'), summary)

    # ---- pairwise comparison + sequence-level statistics
    by = {(r['codec'], r['input_id']): r for r in per}
    comp, seq, tests = [], [], []
    ours_list = [OURS] + (['bdlc_loso'] if loso else [])
    for ours in ours_list:
        for s in scopes:
            for ref in status['codecs']:
                if ref == ours:
                    continue
                ids = sorted(i for i in members[s]
                             if (ref, i) in by and (i in loso if ours == 'bdlc_loso' else (OURS, i) in by))
                if not ids:
                    continue

                def B_o(i):
                    return loso[i] if ours == 'bdlc_loso' else by[(OURS, i)]['bytes']
                timed = ours != 'bdlc_loso'
                Bo, Br = sum(B_o(i) for i in ids), sum(by[(ref, i)]['bytes'] for i in ids)
                row = {'dataset': s, 'ours': ours, 'reference': ref, 'paired_images': len(ids),
                       'full_coverage': len(ids) == n_images(s), 'sum_bytes_ours': Bo, 'sum_bytes_ref': Br,
                       'size_gain_pct': 100 * (1 - Bo / Br),
                       'size_wins': sum(B_o(i) < by[(ref, i)]['bytes'] for i in ids),
                       'size_ties': sum(B_o(i) == by[(ref, i)]['bytes'] for i in ids),
                       'size_losses': sum(B_o(i) > by[(ref, i)]['bytes'] for i in ids)}
                if timed:
                    o = {i: by[(OURS, i)] for i in ids}
                    r_ = {i: by[(ref, i)] for i in ids}
                    teo, ter = sum(o[i]['encode_s'] for i in ids), sum(r_[i]['encode_s'] for i in ids)
                    tdo, tdr = sum(o[i]['decode_s'] for i in ids), sum(r_[i]['decode_s'] for i in ids)
                    row.update(encode_speedup=ter / teo, decode_speedup=tdr / tdo,
                               encode_time_reduction_pct=100 * (1 - teo / ter),
                               decode_time_reduction_pct=100 * (1 - tdo / tdr),
                               encode_wins=sum(o[i]['encode_s'] < r_[i]['encode_s'] for i in ids),
                               decode_wins=sum(o[i]['decode_s'] < r_[i]['decode_s'] for i in ids),
                               joint_size_encode_wins=sum(o[i]['bytes'] < r_[i]['bytes'] and o[i]['encode_s'] < r_[i]['encode_s'] for i in ids),
                               joint_size_encode_decode_wins=sum(o[i]['bytes'] < r_[i]['bytes'] and o[i]['encode_s'] < r_[i]['encode_s']
                                                                 and o[i]['decode_s'] < r_[i]['decode_s'] for i in ids))
                # sequence (cluster) level
                groups = sorted({audit[i]['group'] for i in ids})
                tot, dsz, denc, ddec = [], [], [], []
                for g in groups:
                    gi = [i for i in ids if audit[i]['group'] == g]
                    bo, br = sum(B_o(i) for i in gi), sum(by[(ref, i)]['bytes'] for i in gi)
                    srow = {'dataset': s, 'ours': ours, 'reference': ref, 'group': g, 'images': len(gi),
                            'bytes_ours': bo, 'bytes_ref': br, 'size_gain_pct': 100 * (1 - bo / br)}
                    tot.append([bo, br])
                    dsz.append(math.log(bo / br))
                    if timed:
                        eo, er = sum(by[(OURS, i)]['encode_s'] for i in gi), sum(by[(ref, i)]['encode_s'] for i in gi)
                        do, dr = sum(by[(OURS, i)]['decode_s'] for i in gi), sum(by[(ref, i)]['decode_s'] for i in gi)
                        srow.update(encode_speedup=er / eo, decode_speedup=dr / do)
                        denc.append(math.log(eo / er))
                        ddec.append(math.log(do / dr))
                    if s != POOLED:
                        seq.append(srow)
                lo, hi = cluster_bootstrap(tot)
                row.update(groups=len(groups), seq_size_wins=sum(x < 0 for x in dsz), ci95_low=lo, ci95_high=hi)
                comp.append(row)
                for metric, d in (('size', dsz), ('encode_time', denc), ('decode_time', ddec)):
                    if not d:
                        continue
                    w = sum(x < 0 for x in d)
                    p1, p2 = sign_test(w, len(d))
                    nw, W, pw = wilcoxon_exact(d)
                    tests.append({'dataset': s, 'ours': ours, 'reference': ref, 'metric': metric,
                                  'n_groups': len(d), 'groups_ours_better': w, 'sign_p_one_sided': p1,
                                  'sign_p_two_sided': p2, 'min_attainable_p_one_sided': 0.5 ** len(d),
                                  'wilcoxon_n': nw, 'wilcoxon_W_plus': W, 'wilcoxon_p_one_sided': pw,
                                  'interpretation': 'descriptive' if 0.5 ** len(d) > 0.05 else 'testable'})
    fields = ['dataset', 'ours', 'reference', 'paired_images', 'full_coverage', 'sum_bytes_ours', 'sum_bytes_ref',
              'size_gain_pct', 'size_wins', 'size_ties', 'size_losses', 'encode_speedup', 'decode_speedup',
              'encode_time_reduction_pct', 'decode_time_reduction_pct', 'encode_wins', 'decode_wins',
              'joint_size_encode_wins', 'joint_size_encode_decode_wins', 'groups', 'seq_size_wins', 'ci95_low', 'ci95_high']
    csvout(os.path.join(root, 'comparison.csv'), comp, fields)
    os.makedirs(os.path.join(root, 'statistics'), exist_ok=True)
    csvout(os.path.join(root, 'statistics', 'sequence_level.csv'), seq,
           ['dataset', 'ours', 'reference', 'group', 'images', 'bytes_ours', 'bytes_ref', 'size_gain_pct',
            'encode_speedup', 'decode_speedup'])
    csvout(os.path.join(root, 'statistics', 'tests.csv'), tests)

    # ---- cold start
    cold = []
    for c in status['codecs']:
        p = os.path.join(root, 'coldstart', c + '.json')
        if not os.path.exists(p):
            continue
        runs = jload(p)
        for mode in sorted({r['cache_mode'] for r in runs}):
            rr = [r for r in runs if r['cache_mode'] == mode and r['ok']]
            if rr:
                cold.append({'codec': c, 'numba_cache': mode, 'runs': len(rr),
                             **{k.replace('_ns', '_ms'): float(np.median([r[k] for r in rr])) / 1e6
                                for k in ('import_ns', 'first_encode_ns', 'first_decode_ns', 'second_encode_ns', 'second_decode_ns')}})
    csvout(os.path.join(root, 'statistics', 'coldstart.csv'), cold)

    _paper_tables(root, status, summary, comp, cold)
    _figures(root, status, summary, per)
    return summary


# ------------------------------------------------------------------ paper tables
def _paper_tables(root, status, summary, comp, cold):
    pt = os.path.join(root, 'paper', 'tables')
    os.makedirs(pt, exist_ok=True)
    head = '**%s / %s** (development sizes of `bdlc` use table T1 built from these images; see `bdlc_loso`)' % (
        status['scope'], status['status']) if status['split'] == 'development' else '**%s / %s**' % (status['scope'], status['status'])
    md = ['# Summary', '', head, '']
    tex = []
    for s in sorted({r['dataset'] for r in summary}):
        rs = sorted([r for r in summary if r['dataset'] == s], key=lambda r: r['micro_bpp'])
        md += ['## ' + short(s), '', '| Codec | Images | micro bpp | macro bpp | CR | Encode MPix/s | Decode MPix/s |',
               '|---|---:|---:|---:|---:|---:|---:|']
        tex += ['%% ' + short(s), '\\begin{tabular}{lrrrrr}', 'Codec & N & bpp & CR & Enc.\\ MPix/s & Dec.\\ MPix/s \\\\', '\\hline']
        for r in rs:
            flag = '' if r['full_coverage'] else ' (partial)'
            md.append('| %s%s | %d | %.6f | %.6f | %.1f | %s | %s |' % (
                r['codec'], flag, r['images'], r['micro_bpp'], r['macro_bpp'], r['CR'],
                fmt(r['encode_MPix_s'], 2), fmt(r['decode_MPix_s'], 2)))
            tex.append('%s & %d & %.5f & %.0f & %s & %s \\\\' % (
                r['codec'].replace('_', '\\_') + flag, r['images'], r['micro_bpp'], r['CR'],
                fmt(r['encode_MPix_s'], 1), fmt(r['decode_MPix_s'], 1)))
        md.append('')
        tex += ['\\end{tabular}', '']
    with open(os.path.join(pt, 'summary.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(md))
    with open(os.path.join(pt, 'summary.tex'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(tex))

    md = ['# BDLC vs references', '', head, '',
          '| Scope | Ours | Reference | Images | Size gain % | Size wins | Enc. speedup | Dec. speedup | Joint size+enc wins | Groups won |',
          '|---|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in comp:
        if r['reference'] not in KEY_REFS:
            continue
        md.append('| %s | %s | %s | %d | %.2f | %d/%d | %s | %s | %s | %d/%d |' % (
            short(r['dataset']), r['ours'], r['reference'], r['paired_images'], r['size_gain_pct'],
            r['size_wins'], r['paired_images'], fmt(r.get('encode_speedup', ''), 2), fmt(r.get('decode_speedup', ''), 2),
            '' if r.get('joint_size_encode_wins') is None else '%d/%d' % (r['joint_size_encode_wins'], r['paired_images']),
            r['seq_size_wins'], r['groups']))
    with open(os.path.join(pt, 'comparison.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(md))
    if cold:
        md = ['# Cold start (fresh process, OS file cache warm; medians)', '',
              '| Codec | Numba cache | Runs | Import ms | 1st encode ms | 1st decode ms | 2nd encode ms | 2nd decode ms |',
              '|---|---|---:|---:|---:|---:|---:|---:|']
        for r in cold:
            md.append('| %s | %s | %d | %.1f | %.2f | %.2f | %.3f | %.3f |' % (
                r['codec'], r['numba_cache'], r['runs'], r['import_ms'], r['first_encode_ms'], r['first_decode_ms'],
                r['second_encode_ms'], r['second_decode_ms']))
        with open(os.path.join(pt, 'coldstart.md'), 'w', encoding='utf-8') as f:
            f.write('\n'.join(md))


# ------------------------------------------------------------------ figures
def _style(plt):
    plt.rcParams.update({'font.family': ['Segoe UI', 'DejaVu Sans'], 'font.size': 9, 'axes.edgecolor': AXIS,
                         'axes.labelcolor': INK2, 'xtick.color': INK2, 'ytick.color': INK2, 'axes.titlecolor': INK,
                         'axes.grid': True, 'grid.color': GRID, 'grid.linewidth': 0.6, 'grid.linestyle': '-',
                         'axes.axisbelow': True, 'figure.facecolor': SURF, 'axes.facecolor': SURF,
                         'savefig.facecolor': SURF, 'axes.spines.top': False, 'axes.spines.right': False})


def _plain_log(ax, axes='x'):
    from matplotlib.ticker import FuncFormatter, LogLocator
    f = FuncFormatter(lambda v, _: '%g' % v)
    for a in axes:
        axis = ax.xaxis if a == 'x' else ax.yaxis
        axis.set_major_locator(LogLocator(base=10, subs=(1.0, 2.0, 5.0)))
        axis.set_major_formatter(f)
        axis.set_minor_formatter(FuncFormatter(lambda v, _: ''))


def _save(fig, root, name):
    for ext in ('png', 'pdf', 'svg'):
        fig.savefig(os.path.join(root, 'paper', 'figures', name + '.' + ext), dpi=200, bbox_inches='tight')


def _pareto(pts):
    """Indices of points not dominated (higher x better, lower y better)."""
    keep = []
    for i, (x, y) in enumerate(pts):
        if not any((x2 >= x and y2 <= y) and (x2 > x or y2 < y) for j, (x2, y2) in enumerate(pts) if j != i):
            keep.append(i)
    return sorted(keep, key=lambda i: pts[i][0])


def _figures(root, status, summary, per):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    _style(plt)
    pd = os.path.join(root, 'plot_data')
    tag = '%s / %s' % (status['scope'], status['status'])
    for s in sorted({r['dataset'] for r in summary}):
        rs = [r for r in summary if r['dataset'] == s and r['full_coverage'] and r['encode_MPix_s'] != '']
        if not rs:
            continue
        name = short(s)
        for metric, label, better in (('micro_bpp', 'micro bpp (log scale, lower is better)', 'low'),
                                      ('encode_MPix_s', 'encode throughput, MPix/s (log scale, higher is better)', 'high'),
                                      ('decode_MPix_s', 'decode throughput, MPix/s (log scale, higher is better)', 'high')):
            rr = sorted(rs, key=lambda r: r[metric], reverse=(better == 'low'))
            csvout(os.path.join(pd, '%s_%s.csv' % (name, metric)),
                   [{'dataset': s, 'codec': r['codec'], metric: r[metric], 'images': r['images']} for r in rr])
            fig, ax = plt.subplots(figsize=(7.2, 0.22 * len(rr) + 1.2))
            y = np.arange(len(rr))
            ax.barh(y, [r[metric] for r in rr], height=0.62,
                    color=[HL if r['family'] == 'BDLC' else OTHER for r in rr])
            ax.set_yticks(y, [r['codec'] for r in rr])
            for t, r in zip(ax.get_yticklabels(), rr):
                t.set_color(INK if r['family'] == 'BDLC' else INK2)
            ax.set_xscale('log')
            _plain_log(ax, 'x')
            ax.grid(axis='y', visible=False)
            ax.set_xlabel(label)
            ax.set_title('%s: %s  (%s, %d images)' % (name, metric, tag, rr[0]['images']), loc='left', fontsize=9)
            best_other = (min if better == 'low' else max)((r for r in rr if r['family'] != 'BDLC'), key=lambda r: r[metric])
            for k, r in enumerate(rr):
                if r['codec'] == OURS or r is best_other:
                    ax.annotate(('%.4g' % r[metric]), (r[metric], k), xytext=(4, 0), textcoords='offset points',
                                va='center', fontsize=8, color=INK)
            _save(fig, root, '%s_%s' % (name, metric))
            plt.close(fig)
        # Pareto: BDLC (main configuration) against the competitors; ablations stay in the tables
        rp = [r for r in rs if r['family'] != 'BDLC' or r['codec'] == OURS]
        for speed in ('encode_MPix_s', 'decode_MPix_s'):
            pts = [(r[speed], r['micro_bpp']) for r in rp]
            front = _pareto(pts)
            csvout(os.path.join(pd, '%s_pareto_%s.csv' % (name, speed)),
                   [{'codec': r['codec'], speed: r[speed], 'micro_bpp': r['micro_bpp'], 'pareto': k in front}
                    for k, r in enumerate(rp)])
            fig, ax = plt.subplots(figsize=(7.2, 4.6))
            ax.plot([pts[i][0] for i in front], [pts[i][1] for i in front], color=MUTED, lw=1, zorder=1,
                    label='Pareto front')
            for r in rp:
                ax.scatter(r[speed], r['micro_bpp'], s=42 if r['codec'] == OURS else 26, zorder=3,
                           color=HL if r['codec'] == OURS else OTHER, edgecolor=SURF, linewidth=1.5)
            ax.scatter([], [], s=42, color=HL, label='BDLC')
            ax.scatter([], [], s=26, color=OTHER, label='other codecs')
            ax.legend(frameon=False, fontsize=8, loc='upper left')
            ax.set_xscale('log')
            ax.set_yscale('log')
            _plain_log(ax, 'xy')
            fig.canvas.draw()
            prio = [OURS] + [rp[i]['codec'] for i in front] + ['jpegls', 'zstd3', 'jpegxl9', 'jpegxl10',
                                                                'crackle_mo0_zstd19', 'crackle_mo3_zstd19', 'lzma9e']
            placed = []
            for c in dict.fromkeys(prio):
                r = next((q for q in rp if q['codec'] == c), None)
                if r is None:
                    continue
                px, py = ax.transData.transform((r[speed], r['micro_bpp'])) * 72.0 / fig.dpi   # points
                wpt = 4.3 * len(c) + 2
                for dx, dy in ((4, 2), (4, -10), (-wpt - 4, 2), (-wpt - 4, -10)):
                    box = (px + dx, py + dy, px + dx + wpt, py + dy + 8.5)
                    if all(box[2] < b[0] or box[0] > b[2] or box[3] < b[1] or box[1] > b[3] for b in placed):
                        placed.append(box)
                        ax.annotate(c, (r[speed], r['micro_bpp']), xytext=(dx, dy), textcoords='offset points',
                                    fontsize=7.5, color=INK if c == OURS else INK2)
                        break
            ax.set_xlabel(speed.replace('_MPix_s', ' throughput, MPix/s (log, right is better)'))
            ax.set_ylabel('micro bpp (log, down is better)')
            ax.set_title('%s: size vs %s speed, Pareto front in gray  (%s)' % (name, speed[:6], tag), loc='left', fontsize=9)
            _save(fig, root, '%s_pareto_%s' % (name, speed))
            plt.close(fig)

    # per-image paired size ratios vs key references
    refs = [c for c in KEY_REFS if c in status['codecs']]
    ours = {r['input_id']: r for r in per if r['codec'] == OURS}
    dsets = sorted({r['dataset'] for r in per})
    rows = []
    for ref in refs:
        for r in per:
            if r['codec'] == ref and r['input_id'] in ours:
                rows.append({'reference': ref, 'dataset': r['dataset'], 'input_id': r['input_id'],
                             'ratio_bytes_bdlc_over_ref': ours[r['input_id']]['bytes'] / r['bytes']})
    if rows:
        csvout(os.path.join(pd, 'paired_ratio.csv'), rows)
        fig, ax = plt.subplots(figsize=(7.2, 0.34 * len(refs) + 1.4))
        rng = np.random.default_rng(1)
        for k, ref in enumerate(refs):
            for j, ds in enumerate(dsets):
                v = [q['ratio_bytes_bdlc_over_ref'] for q in rows if q['reference'] == ref and q['dataset'] == ds]
                if v:
                    yy = k + (j - (len(dsets) - 1) / 2) * 0.22 + rng.uniform(-0.06, 0.06, len(v))
                    ax.scatter(v, yy, s=9, color=DS_COLORS[j % 3], edgecolor='none', alpha=0.85,
                               label=short(ds) if k == 0 else None)
            v = [q['ratio_bytes_bdlc_over_ref'] for q in rows if q['reference'] == ref]
            ax.annotate('%d/%d smaller' % (sum(x < 1 for x in v), len(v)), (1.0, k), xytext=(6, -3),
                        textcoords='offset points', fontsize=7, color=INK2)
        ax.axvline(1.0, color=INK2, lw=0.8)
        ax.set_yticks(range(len(refs)), refs)
        ax.invert_yaxis()
        ax.set_xscale('log')
        _plain_log(ax, 'x')
        ax.grid(axis='y', visible=False)
        ax.set_xlabel('per-image stream size ratio  B_bdlc / B_ref  (log; left of 1 = BDLC smaller)')
        ax.set_title('Per-image paired sizes (%s)' % tag, loc='left', fontsize=9, pad=22)
        ax.legend(frameon=False, fontsize=8, loc='lower left', bbox_to_anchor=(0, 1.0), ncol=3,
                  handletextpad=0.2, borderaxespad=0.2)
        _save(fig, root, 'paired_size_ratio')
        plt.close(fig)

    with open(os.path.join(root, 'paper', 'CAPTIONS.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join([
            '# Figure notes', '',
            '* Every figure is drawn from the CSV of the same name in `plot_data/` (the table view).',
            '* Sizes are full self-contained streams (headers, palettes and varint H/W wrappers included).',
            '* Times are medians of the timed repeats of each image, in-process, warm, one pinned logical CPU at high',
            '  priority, garbage collector off, file I/O excluded; throughput = sum pixels / sum median time.',
            '* BDLC is a Numba (LLVM JIT) implementation, the other codecs are native C/C++ libraries behind Python',
            '  bindings: speed is an implementation comparison. JIT compilation happens in warm-up; see coldstart.',
            '* Only codecs with full image coverage are drawn. Highlighted (blue) = BDLC family.',
            '* Development figures: `bdlc` uses table T1 trained on these same images (in-sample); the honest',
            '  development size is `bdlc_loso` in tables/summary.csv and comparison.csv.',
        ]))


if __name__ == '__main__':
    build(sys.argv[1])
    print('report rebuilt:', sys.argv[1])
