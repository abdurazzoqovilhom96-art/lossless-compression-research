"""Results generator: every table, figure, statistic and report of one benchmark run, from that run's
stored measurements only (no benchmark is re-run, no value is typed in or estimated).

  python bench/make_reports.py RUN_DIR            -> RUN_DIR/results/   (replaces only results/)

Primary measurement set (one table, tables/per_image.csv): a (codec, image) pair enters only if its
stream was decoded to the source pixels in an independent process (verification/<codec>.json, same
stream SHA-256). Sizes come from raw_size/ (two-phase runs) or raw/ (single-phase runs); timings come
from raw/ (the pinned timing phase). Timings of command-line codecs are net of the median null (1x1)
call. A missing or failed measurement is left empty, never written as 0.

results/
  tables/        per_image.csv, summary_by_dataset.csv, pairwise_vs_bdlc.csv
  statistics/    size_gain.csv, speed_coefficients.csv, wins.csv, sequence_level.csv,
                 virtual_best.csv, protocol_B_tests.csv (if ECC is present), coldstart.csv
  plot_data/     one CSV per figure (the exact plotted values)
  figures/       PNG (300 dpi) per figure
  paper/tables/  Markdown and LaTeX tables;   paper/figures/  PDF, SVG and PNG (300 dpi)
  reports/       NATIJALAR_UZ.md, status.json (reporting status; the run's own status.json is
                 never touched), errors.md, artifact_manifest.json
A result that cannot be produced gets a NOT_GENERATED.md in its folder (reason, missing data) and
makes reporting_status PARTIAL; it is never counted as generated.
"""
import argparse
import csv
import json
import math
import os
import shutil
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.dirname(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import backends  # noqa: E402

OURS = 'bdlc'
POOLED = 'ALL_REAL'
FOLDERS = ['tables', 'statistics', 'plot_data', 'figures', 'paper/tables', 'paper/figures', 'reports']
NAMES = {
    'bdlc': 'BDLC (ours)', 'bdlc_crc': 'BDLC +CRC', 'bdlc_uniform': 'BDLC uniform init',
    'bdlc_noslope': 'BDLC no slope', 'bdlc_nok2': 'BDLC no k2', 'bdlc_nopass': 'BDLC no PASS',
    'rvc': 'RVC (legacy)', 'zlib9': 'zlib -9', 'lzma9e': 'xz -9e', 'zstd3': 'Zstandard -3',
    'zstd19': 'Zstandard -19', 'brotli11': 'Brotli -11', 'bz2_9': 'bzip2 -9',
    'blosc2_zstd_bitshuffle': 'Blosc2 zstd+bitshuffle', 'png16': 'PNG 16-bit', 'jpegls': 'JPEG-LS',
    'jpegxl7': 'JPEG XL e7', 'jpegxl9': 'JPEG XL e9', 'jpegxl10': 'JPEG XL e10', 'jpeg2k': 'JPEG 2000',
    'htj2k': 'HTJ2K', 'lerc': 'LERC', 'lerc_zstd': 'LERC + zstd', 'palette_zstd19': 'palette + zstd -19',
    'palette_lzma9e': 'palette + xz -9e', 'crackle_mo0': 'Crackle mo0', 'crackle_mo3': 'Crackle mo3',
    'crackle_mo0_zstd19': 'Crackle mo0 + zstd', 'crackle_mo3_zstd19': 'Crackle mo3 + zstd',
    'cseg_gzip9': 'compressed_segmentation + gzip', 'ecc_direct': 'ECC-2026', 'ecc_pi': 'ECC-2026 (rank map)',
    'hevc_scc_direct': 'HEVC SCC', 'hevc_scc_pi': 'HEVC SCC (rank map)', 'jbig_gray_pi': 'JBIG1 (Gray)',
    'jbig_binary_pi': 'JBIG1 (binary)', 'flif_u16_e60': 'FLIF 16-bit', 'flif_u16_e100': 'FLIF 16-bit -E100',
    'flif_pi_e60': 'FLIF rank map', 'flif_pi_e100': 'FLIF rank map -E100', 'compresso': 'Compresso',
}
HL, OTHER, INK = '#1f5fbf', '#9a9a9a', '#222222'
TOL = 1e-9


# ------------------------------------------------------------------ small helpers
def name(c):
    return NAMES.get(c, c)


def jload(p):
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def csv_write(path, rows, fields):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator='\n', extrasaction='ignore')
        w.writeheader()
        for r in rows:
            w.writerow({k: ('' if r.get(k) is None else r.get(k)) for k in fields})


def csv_read(path):
    with open(path, encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def fnum(x):
    return None if x in (None, '') else float(x)


def is_ours_family(c):
    return backends.SPEC.get(c, ('?',))[0] == 'BDLC'


def safe(s):
    return ''.join(ch if ch.isalnum() or ch in '-_' else '_' for ch in s)


# ------------------------------------------------------------------ statistics
def binom_tail_ge(w, n):
    return sum(math.comb(n, k) for k in range(w, n + 1)) / 2 ** n


def sign_test(d):
    """d: per-cluster log ratios (ours/ref). Ties dropped. Returns n, ours_better, p_one (ours better), p_two."""
    d = [x for x in d if x != 0]
    n = len(d)
    if not n:
        return 0, 0, None, None
    w = sum(x < 0 for x in d)
    p1 = binom_tail_ge(w, n)
    p_low = binom_tail_ge(n - w, n)
    return n, w, p1, min(1.0, 2 * min(p1, p_low))


def wilcoxon(d):
    """Signed-rank test on per-cluster log ratios; exact for n <= 50 without ties, else normal approx.
    Returns n, W+ (sum of ranks of positive d), p_one (median < 0), p_two, method."""
    d = np.array([x for x in d if x != 0], float)
    n = len(d)
    if not n:
        return 0, None, None, None, ''
    a = np.abs(d)
    order = np.argsort(a, kind='mergesort')
    ranks = np.empty(n)
    i = 0
    while i < n:
        j = i
        while j + 1 < n and a[order[j + 1]] == a[order[i]]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2 + 1
        i = j + 1
    wp = float(ranks[d > 0].sum())
    ties = len(np.unique(a)) < n
    if n <= 50 and not ties:
        S = n * (n + 1) // 2
        cnt = np.zeros(S + 1)
        cnt[0] = 1
        for k in range(1, n + 1):
            cnt[k:] = cnt[k:] + cnt[:-k].copy()
        cdf = np.cumsum(cnt) / 2 ** n
        w = int(round(wp))
        p_le = cdf[w]
        p_ge = 1 - (cdf[w - 1] if w > 0 else 0)
        return n, wp, float(p_le), float(min(1.0, 2 * min(p_le, p_ge))), 'exact'
    mu = n * (n + 1) / 4
    _, tc = np.unique(a, return_counts=True)
    var = n * (n + 1) * (2 * n + 1) / 24 - float((tc ** 3 - tc).sum()) / 48
    z = (wp - mu) / math.sqrt(var) if var > 0 else 0.0
    p_le = 0.5 * math.erfc(-z / math.sqrt(2))
    return n, wp, p_le, min(1.0, 2 * min(p_le, 1 - p_le)), 'normal'


def boot_ci(d, reps=10000, seed=20261029):
    d = np.asarray(d, float)
    if len(d) < 2:
        return None, None
    rng = np.random.default_rng(seed)
    m = d[rng.integers(0, len(d), (reps, len(d)))].mean(axis=1)
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def holm(ps):
    idx = [i for i, p in enumerate(ps) if p is not None]
    out = [None] * len(ps)
    run = 0.0
    for r, i in enumerate(sorted(idx, key=lambda i: ps[i])):
        run = max(run, min(1.0, (len(idx) - r) * ps[i]))
        out[i] = run
    return out


def delta_pct(dbar):
    return None if dbar is None else 100 * (1 - math.exp(dbar))


# ------------------------------------------------------------------ primary measurement set
def load_primary(run):
    status = jload(os.path.join(run, 'status.json'))
    proto = jload(os.path.join(run, 'provenance', 'freeze.json'))
    audit = {r['input_id']: r for r in jload(os.path.join(run, 'provenance', 'input_audit.json'))}
    two = os.path.isdir(os.path.join(run, 'raw_size'))
    issues, per = [], []
    for c in status['codecs']:
        sp = os.path.join(run, 'raw_size' if two else 'raw', c + '.json')
        vp = os.path.join(run, 'verification', c + '.json')
        tp = os.path.join(run, 'raw', c + '.json')
        if not (os.path.exists(sp) and os.path.exists(vp)):
            issues.append({'codec': c, 'issue': 'size or verification file missing; codec has no primary rows'})
            continue
        sizes = jload(sp)['images']
        ver = {v['input_id']: v for v in jload(vp)['images']}
        traw = jload(tp) if os.path.exists(tp) else {}
        timing = {m['input_id']: m for m in traw.get('images', [])}
        null = traw.get('null', {})
        cli = backends.SPEC.get(c, ('', ''))[1] == 'cli'
        ne = null.get('enc_median_ns', 0) / 1e9 if cli else 0.0
        nd = null.get('dec_median_ns', 0) / 1e9 if cli else 0.0
        if cli and 'enc_median_ns' not in null and timing:
            issues.append({'codec': c, 'issue': 'command-line codec without null-run timing; timings not used'})
            timing = {}
        for m in sizes:
            iid = m['input_id']
            v = ver.get(iid)
            if not v or not v.get('ok') or v.get('stream_sha256') != m['stream_sha256']:
                issues.append({'codec': c, 'input_id': iid, 'issue': 'not verified in an independent decode; excluded'})
                continue
            a = audit[iid]
            n = int(a['pixels'])
            row = {'input_id': iid, 'dataset': a['dataset'], 'group': a['group'],
                   'synthetic': str(a.get('synthetic', 'false')).lower() == 'true', 'pixels': n, 'K': a['K'],
                   'codec': c, 'codec_name': name(c), 'family': backends.SPEC.get(c, ('?',))[0],
                   'bytes': int(m['bytes']), 'stream_bytes': int(m.get('stream_bytes', m['bytes'])),
                   'bpp': 8 * int(m['bytes']) / n, 'verified': True, 'timed': False, 'repeats': None,
                   'encode_s': None, 'decode_s': None, 'encode_MPix_s': None, 'decode_MPix_s': None,
                   'encode_s_raw': None, 'decode_s_raw': None, 'null_encode_s': None, 'null_decode_s': None,
                   'deterministic': None}
            t = timing.get(iid)
            if t is not None and 'enc_median_ns' in t:
                if t['stream_sha256'] != m['stream_sha256']:
                    issues.append({'codec': c, 'input_id': iid, 'issue': 'timed stream differs from verified stream; timing excluded'})
                else:
                    er, dr = t['enc_median_ns'] / 1e9, t['dec_median_ns'] / 1e9
                    te, td = er - ne, dr - nd
                    if te <= 0 or td <= 0:
                        issues.append({'codec': c, 'input_id': iid, 'issue': 'net time <= 0 after null subtraction; timing excluded'})
                    else:
                        row.update(timed=True, repeats=len(t['enc_ns']), encode_s=te, decode_s=td,
                                   encode_MPix_s=n / te / 1e6, decode_MPix_s=n / td / 1e6, encode_s_raw=er,
                                   decode_s_raw=dr, null_encode_s=ne if cli else None,
                                   null_decode_s=nd if cli else None, deterministic=t.get('deterministic'))
            per.append(row)
    per.sort(key=lambda r: (r['dataset'], r['input_id'], r['codec']))
    return status, proto, audit, per, issues, two


def scopes_of(audit):
    ds = {}
    for iid, a in audit.items():
        ds.setdefault(a['dataset'], set()).add(iid)
    mem = dict(ds)
    real = {i for i, a in audit.items() if str(a.get('synthetic', 'false')).lower() != 'true'}
    if real and len([d for d in ds if ds[d] & real]) > 1:
        mem[POOLED] = real
    return mem


# ------------------------------------------------------------------ derived tables
SUMMARY_FIELDS = ['scope', 'codec', 'codec_name', 'family', 'scope_images', 'images_sized', 'size_coverage',
                  'total_bytes', 'total_pixels', 'micro_bpp', 'macro_bpp', 'CR', 'images_timed', 'timed_pixels',
                  'repeats_min', 'repeats_max', 'encode_s_sum', 'decode_s_sum', 'encode_MPix_s', 'decode_MPix_s']


def summary_table(per, mem):
    out = []
    for s in sorted(mem):
        for c in sorted({r['codec'] for r in per}):
            rs = [r for r in per if r['codec'] == c and r['input_id'] in mem[s]]
            if not rs:
                continue
            N = sum(r['pixels'] for r in rs)
            B = sum(r['bytes'] for r in rs)
            ts = [r for r in rs if r['timed']]
            row = {'scope': s, 'codec': c, 'codec_name': name(c), 'family': rs[0]['family'],
                   'scope_images': len(mem[s]), 'images_sized': len(rs), 'size_coverage': len(rs) / len(mem[s]),
                   'total_bytes': B, 'total_pixels': N, 'micro_bpp': 8 * B / N,
                   'macro_bpp': float(np.mean([r['bpp'] for r in rs])), 'CR': 16 / (8 * B / N),
                   'images_timed': len(ts)}
            if ts:
                tp = sum(r['pixels'] for r in ts)
                te = sum(r['encode_s'] for r in ts)
                td = sum(r['decode_s'] for r in ts)
                row.update(timed_pixels=tp, repeats_min=min(r['repeats'] for r in ts),
                           repeats_max=max(r['repeats'] for r in ts), encode_s_sum=te, decode_s_sum=td,
                           encode_MPix_s=tp / te / 1e6, decode_MPix_s=tp / td / 1e6)
            out.append(row)
    return out


PAIR_FIELDS = ['scope', 'ours', 'reference', 'reference_name', 'scope_images', 'n_common', 'sum_bytes_ours',
               'sum_bytes_ref', 'size_gain_pct', 'size_result', 'size_wins', 'size_ties', 'size_losses',
               'n_timed_common', 'encode_s_ours', 'encode_s_ref', 'encode_speedup', 'decode_s_ours', 'decode_s_ref',
               'decode_speedup', 'encode_wins', 'encode_losses', 'decode_wins', 'decode_losses',
               'joint_size_encode_decode_wins']


def pairwise(per, mem, ours=OURS):
    by = {(r['codec'], r['input_id']): r for r in per}
    codecs = sorted({r['codec'] for r in per})
    out = []
    for s in sorted(mem):
        for ref in codecs:
            if ref == ours:
                continue
            ids = sorted(i for i in mem[s] if (ours, i) in by and (ref, i) in by)
            if not ids:
                continue
            o = [by[(ours, i)] for i in ids]
            r = [by[(ref, i)] for i in ids]
            Bo, Br = sum(x['bytes'] for x in o), sum(x['bytes'] for x in r)
            g = 100 * (1 - Bo / Br)
            row = {'scope': s, 'ours': ours, 'reference': ref, 'reference_name': name(ref), 'scope_images': len(mem[s]),
                   'n_common': len(ids), 'sum_bytes_ours': Bo, 'sum_bytes_ref': Br, 'size_gain_pct': g,
                   'size_result': 'ours smaller' if Bo < Br else ('ours larger' if Bo > Br else 'equal'),
                   'size_wins': sum(a['bytes'] < b['bytes'] for a, b in zip(o, r)),
                   'size_ties': sum(a['bytes'] == b['bytes'] for a, b in zip(o, r)),
                   'size_losses': sum(a['bytes'] > b['bytes'] for a, b in zip(o, r))}
            tt = [(a, b) for a, b in zip(o, r) if a['timed'] and b['timed']]
            row['n_timed_common'] = len(tt)
            if tt:
                eo, er = sum(a['encode_s'] for a, _ in tt), sum(b['encode_s'] for _, b in tt)
                do, dr = sum(a['decode_s'] for a, _ in tt), sum(b['decode_s'] for _, b in tt)
                row.update(encode_s_ours=eo, encode_s_ref=er, encode_speedup=er / eo, decode_s_ours=do,
                           decode_s_ref=dr, decode_speedup=dr / do,
                           encode_wins=sum(a['encode_s'] < b['encode_s'] for a, b in tt),
                           encode_losses=sum(a['encode_s'] > b['encode_s'] for a, b in tt),
                           decode_wins=sum(a['decode_s'] < b['decode_s'] for a, b in tt),
                           decode_losses=sum(a['decode_s'] > b['decode_s'] for a, b in tt),
                           joint_size_encode_decode_wins=sum(a['bytes'] < b['bytes'] and a['encode_s'] < b['encode_s']
                                                             and a['decode_s'] < b['decode_s'] for a, b in tt))
            out.append(row)
    return out


def cluster_logs(per, mem, s, ours, refs, metric='bytes', oracle=False):
    """Per cluster: ln(sum ours / sum ref). With oracle=True the reference of each image is the smallest
    of `refs` available for it. Only images with ours and (all needed) refs present; timed images for times."""
    by = {(r['codec'], r['input_id']): r for r in per}
    groups, imgs = {}, 0
    for i in mem[s]:
        if (ours, i) not in by:
            continue
        avail = [by[(c, i)] for c in refs if (c, i) in by]
        if not avail or (not oracle and len(avail) != len(refs)):
            continue
        o = by[(ours, i)]
        if metric != 'bytes' and not (o['timed'] and all(a['timed'] for a in avail)):
            continue
        ref = min(avail, key=lambda a: a['bytes']) if oracle else avail[0]
        g = groups.setdefault(o['group'], [0.0, 0.0])
        g[0] += o[metric]
        g[1] += ref[metric]
        imgs += 1
    names = sorted(groups)
    return names, [math.log(groups[g][0] / groups[g][1]) for g in names], imgs


def stat_rows(per, mem, pair):
    size, speed, wins, seq = [], [], [], []
    for p in pair:
        s, ref = p['scope'], p['reference']
        g, d, n = cluster_logs(per, mem, s, OURS, [ref])
        ns, w, p1, p2 = sign_test(d)
        nw, wp, wp1, wp2, meth = wilcoxon(d)
        dbar = float(np.mean(d)) if d else None
        lo, hi = boot_ci(d)
        size.append({'scope': s, 'reference': ref, 'reference_name': p['reference_name'], 'n_common': p['n_common'],
                     'scope_images': p['scope_images'], 'size_gain_pct': p['size_gain_pct'], 'size_result': p['size_result'],
                     'size_wins': p['size_wins'], 'size_ties': p['size_ties'], 'size_losses': p['size_losses'],
                     'groups': len(g), 'groups_ours_smaller': sum(x < 0 for x in d), 'mean_log_ratio': dbar,
                     'delta_pct_from_mean_log': delta_pct(dbar), 'delta_ci95_low': delta_pct(hi), 'delta_ci95_high': delta_pct(lo),
                     'sign_p_one_sided_ours_smaller': p1, 'sign_p_two_sided': p2, 'wilcoxon_p_one_sided': wp1,
                     'wilcoxon_p_two_sided': wp2, 'wilcoxon_method': meth,
                     'min_attainable_p_one_sided': 0.5 ** ns if ns else None,
                     'interpretation': ('testable' if ns and 0.5 ** ns <= 0.05 else 'descriptive (too few clusters)')})
        row = {'scope': s, 'reference': ref, 'reference_name': p['reference_name'], 'n_timed_common': p['n_timed_common']}
        if p['n_timed_common']:
            ge, de, _ = cluster_logs(per, mem, s, OURS, [ref], 'encode_s')
            gd, dd, _ = cluster_logs(per, mem, s, OURS, [ref], 'decode_s')
            _, we, pe, _ = sign_test(de)
            _, wd, pd_, _ = sign_test(dd)
            row.update(encode_speedup=p['encode_speedup'], decode_speedup=p['decode_speedup'], groups=len(ge),
                       groups_encode_faster=sum(x < 0 for x in de), groups_decode_faster=sum(x < 0 for x in dd),
                       sign_p_encode_faster=pe, sign_p_decode_faster=pd_)
        speed.append(row)
        wins.append({k: p.get(k) for k in ('scope', 'reference', 'reference_name', 'n_common', 'size_wins', 'size_ties',
                                           'size_losses', 'n_timed_common', 'encode_wins', 'encode_losses', 'decode_wins',
                                           'decode_losses', 'joint_size_encode_decode_wins')})
        if s != POOLED:
            by = {(r['codec'], r['input_id']): r for r in per}
            for grp in g:
                ids = [i for i in mem[s] if (OURS, i) in by and (ref, i) in by and by[(OURS, i)]['group'] == grp]
                bo, br = sum(by[(OURS, i)]['bytes'] for i in ids), sum(by[(ref, i)]['bytes'] for i in ids)
                tt = [i for i in ids if by[(OURS, i)]['timed'] and by[(ref, i)]['timed']]
                sr = {'scope': s, 'reference': ref, 'group': grp, 'images': len(ids), 'bytes_ours': bo, 'bytes_ref': br,
                      'size_gain_pct': 100 * (1 - bo / br), 'timed_images': len(tt)}
                if tt:
                    sr['encode_speedup'] = sum(by[(ref, i)]['encode_s'] for i in tt) / sum(by[(OURS, i)]['encode_s'] for i in tt)
                    sr['decode_speedup'] = sum(by[(ref, i)]['decode_s'] for i in tt) / sum(by[(OURS, i)]['decode_s'] for i in tt)
                seq.append(sr)
    return size, speed, wins, seq


def virtual_best(per, mem):
    codecs = sorted({r['codec'] for r in per})
    comp = [c for c in codecs if not is_ours_family(c)]
    ecc = [c for c in comp if c.startswith('ecc_')]
    sets = {'all_competitors': comp}
    if ecc:
        sets['all_except_ECC'] = [c for c in comp if c not in ecc]
        sets['ECC_only'] = ecc
    out = []
    for s in sorted(mem):
        for nm, refs in sets.items():
            if not refs:
                continue
            g, d, n = cluster_logs(per, mem, s, OURS, refs, oracle=True)
            if not d:
                continue
            ns, w, p1, p2 = sign_test(d)
            _, _, wp1, wp2, meth = wilcoxon(d)
            dbar = float(np.mean(d))
            lo, hi = boot_ci(d)
            out.append({'scope': s, 'oracle': nm, 'oracle_members': len(refs), 'images': n, 'groups': len(g),
                        'groups_ours_smaller': sum(x < 0 for x in d), 'mean_log_ratio': dbar,
                        'delta_pct': delta_pct(dbar), 'delta_ci95_low': delta_pct(hi), 'delta_ci95_high': delta_pct(lo),
                        'sign_p_one_sided_ours_smaller': p1, 'sign_p_two_sided': p2, 'wilcoxon_p_one_sided': wp1,
                        'wilcoxon_p_two_sided': wp2, 'wilcoxon_method': meth,
                        'group_log_ratios': ';'.join('%s=%.5f' % (a, b) for a, b in zip(g, d))})
    return out


def protocol_B(per, mem, pair):
    """PROTOKOL_B_UZ.md: B1 size vs ECC (two-sided), B2 size vs best non-ECC competitor (one-sided),
    B3 speed vs ecc_direct (one-sided, encode and decode), Holm over B1-B3; B4 Pareto (descriptive)."""
    codecs = {r['codec'] for r in per}
    ecc = sorted(c for c in codecs if c.startswith('ecc_'))
    if not ecc:
        return [], []
    comp = sorted(c for c in codecs if not is_ours_family(c))
    rest = [c for c in comp if c not in ecc]
    tests, pareto = [], []
    for s in sorted(mem):
        g1, d1, n1 = cluster_logs(per, mem, s, OURS, ecc, oracle=True)
        g2, d2, n2 = cluster_logs(per, mem, s, OURS, rest, oracle=True)
        ref3 = 'ecc_direct' if 'ecc_direct' in codecs else ecc[0]
        g3e, d3e, n3 = cluster_logs(per, mem, s, OURS, [ref3], 'encode_s')
        _, d3d, _ = cluster_logs(per, mem, s, OURS, [ref3], 'decode_s')
        if not d1:
            continue
        _, _, _, p1 = sign_test(d1)
        _, _, _, wp1, _ = wilcoxon(d1)
        _, _, p2, _ = sign_test(d2) if d2 else (0, 0, None, None)
        p3e = sign_test(d3e)[2] if d3e else None
        p3d = sign_test(d3d)[2] if d3d else None
        p3 = max(p3e, p3d) if p3e is not None and p3d is not None else None   # intersection-union
        adj = holm([p1, p2, p3])
        lo1, hi1 = boot_ci(d1)
        lo2, hi2 = boot_ci(d2) if d2 else (None, None)
        rows = [
            {'scope': s, 'hypothesis': 'B1 size vs ECC (oracle of %s), two-sided' % '+'.join(ecc), 'images': n1,
             'groups': len(g1), 'groups_ours_better': sum(x < 0 for x in d1), 'statistic': 'delta_pct',
             'estimate': delta_pct(float(np.mean(d1))), 'ci95_low': delta_pct(hi1), 'ci95_high': delta_pct(lo1),
             'p_sign': p1, 'p_wilcoxon': wp1, 'p_holm': adj[0]},
            {'scope': s, 'hypothesis': 'B2 size vs best non-ECC competitor (%d configurations), one-sided' % len(rest),
             'images': n2, 'groups': len(g2), 'groups_ours_better': sum(x < 0 for x in d2), 'statistic': 'delta_pct',
             'estimate': delta_pct(float(np.mean(d2))) if d2 else None, 'ci95_low': delta_pct(hi2),
             'ci95_high': delta_pct(lo2), 'p_sign': p2, 'p_wilcoxon': wilcoxon(d2)[2] if d2 else None, 'p_holm': adj[1]},
            {'scope': s, 'hypothesis': 'B3 faster than %s in encode and decode, one-sided (intersection-union)' % ref3,
             'images': n3, 'groups': len(g3e), 'groups_ours_better': '%d enc / %d dec' % (sum(x < 0 for x in d3e), sum(x < 0 for x in d3d)),
             'statistic': 'encode/decode speedup (cluster geometric mean)',
             'estimate': '%.3f / %.3f' % (math.exp(-np.mean(d3e)), math.exp(-np.mean(d3d))) if d3e and d3d else None,
             'p_sign': p3, 'p_holm': adj[2]},
        ]
        tests += rows
        for ref in comp:
            gs, ds, _ = cluster_logs(per, mem, s, OURS, [ref])
            ge, de, _ = cluster_logs(per, mem, s, OURS, [ref], 'encode_s')
            gd, dd, _ = cluster_logs(per, mem, s, OURS, [ref], 'decode_s')
            if not (ds and de and dd):
                continue
            S, E, D = dict(zip(gs, ds)), dict(zip(ge, de)), dict(zip(gd, dd))
            common = sorted(set(S) & set(E) & set(D))
            dom = sum(S[g] > 0 and E[g] > 0 and D[g] > 0 for g in common)
            pareto.append({'scope': s, 'reference': ref, 'reference_name': name(ref), 'groups': len(common),
                           'groups_ref_smaller_and_faster_both': dom,
                           'bdlc_pareto_dominated_by_ref': dom > len(common) / 2})
    return tests, pareto


# ------------------------------------------------------------------ figures
def _plt():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 8, 'axes.edgecolor': '#555555',
                         'axes.labelcolor': INK, 'xtick.color': INK, 'ytick.color': INK, 'svg.fonttype': 'path'})
    return plt


def save_fig(fig, res, stem):
    fig.savefig(os.path.join(res, 'figures', stem + '.png'), dpi=300, bbox_inches='tight')
    for ext in ('pdf', 'svg', 'png'):
        fig.savefig(os.path.join(res, 'paper', 'figures', stem + '.' + ext), dpi=300, bbox_inches='tight')


def bar_figure(plt, rows, metric, label, title, res, stem, better):
    rows = sorted(rows, key=lambda r: r[metric], reverse=(better == 'high'))
    h = 0.6 + 0.19 * len(rows)
    fig, ax = plt.subplots(figsize=(6.6, h))
    y = np.arange(len(rows))
    vals = [r[metric] for r in rows]
    ax.barh(y, vals, color=[HL if r['codec'] == OURS else OTHER for r in rows], height=0.7)
    ax.set_yticks(y)
    ax.set_yticklabels([r['codec_name'] for r in rows])
    for t, r in zip(ax.get_yticklabels(), rows):
        if r['codec'] == OURS:
            t.set_fontweight('bold')
            t.set_color(HL)
    ax.invert_yaxis()
    ax.set_xscale('log')
    ax.set_xlabel(label)
    ax.set_title(title, fontsize=9, loc='left')
    for yy, v in zip(y, vals):
        ax.text(v, yy, ' %.4g' % v, va='center', fontsize=6.5, color=INK)
    ax.grid(axis='x', color='#e3e3e3', linewidth=0.6)
    ax.set_axisbelow(True)
    ax.set_xlim(min(vals) / 1.5, max(vals) * 4)
    save_fig(fig, res, stem)
    plt.close(fig)


def scatter_figure(plt, pts, xkey, xlabel, title, res, stem):
    """Size vs speed; BDLC ablation variants are left out (they are not competitors; see bar charts)."""
    pts = [p for p in pts if p['codec'] == OURS or not is_ours_family(p['codec'])]
    fig, ax = plt.subplots(figsize=(6.6, 4.6))
    for p in pts:
        ours = p['codec'] == OURS
        ax.scatter(p[xkey], p['micro_bpp'], s=36 if ours else 16, color=HL if ours else OTHER, zorder=3,
                   edgecolor='white', linewidth=0.6)
    ax.set_xscale('log')
    ax.set_yscale('log')
    xs, ys = [p[xkey] for p in pts], [p['micro_bpp'] for p in pts]
    ax.set_xlim(min(xs) / 2.5, max(xs) * 2.5)
    ax.set_ylim(min(ys) / 1.3, max(ys) * 1.3)
    ax.set_xlabel(xlabel)
    ax.set_ylabel('Size (bits per pixel, log scale; lower is better)')
    ax.set_title(title, fontsize=9, loc='left')
    ax.grid(color='#e3e3e3', linewidth=0.6)
    ax.set_axisbelow(True)
    fig.canvas.draw()
    rnd = fig.canvas.get_renderer()
    from matplotlib.transforms import Bbox
    placed = []   # markers count as obstacles too, so labels never cover a point
    for x, y in ax.transData.transform(list(zip(xs, ys))):
        placed.append(Bbox.from_bounds(x - 4, y - 4, 8, 8))
    offsets = [(4, 2, 'left'), (4, -9, 'left'), (-4, 2, 'right'), (-4, -9, 'right'), (4, 11, 'left'),
               (4, -18, 'left'), (-4, 11, 'right'), (-4, -18, 'right'), (4, 20, 'left'), (4, -27, 'left')]
    for p in sorted(pts, key=lambda p: (p['codec'] != OURS, p['micro_bpp'])):   # greedy, no overlapping labels
        ours = p['codec'] == OURS
        for dx, dy, ha in offsets:
            t = ax.annotate(p['codec_name'], (p[xkey], p['micro_bpp']), xytext=(dx, dy), textcoords='offset points',
                            ha=ha, fontsize=6, color=HL if ours else INK, fontweight='bold' if ours else 'normal')
            bb = t.get_window_extent(rnd).expanded(1.03, 1.15)
            if not any(bb.overlaps(q) for q in placed):
                break
            t.remove()
        else:
            t = ax.annotate(p['codec_name'], (p[xkey], p['micro_bpp']), xytext=(4, 2), textcoords='offset points',
                            fontsize=6, color=HL if ours else INK)
            bb = t.get_window_extent(rnd)
        placed.append(bb)
    save_fig(fig, res, stem)
    plt.close(fig)


def make_figures(res, per, mem, summary, notes):
    plt = _plt()
    figs = []
    by = {(r['codec'], r['input_id']): r for r in per}
    for s in sorted(mem):
        srows = [r for r in summary if r['scope'] == s]
        full = [r for r in srows if r['images_sized'] == r['scope_images']]
        part = [r['codec'] for r in srows if r['images_sized'] != r['scope_images']]
        tag = safe(s)
        if any(r['codec'] == OURS for r in full) and len(full) > 1:
            stem = 'size_%s' % tag
            csv_write(os.path.join(res, 'plot_data', stem + '.csv'), full,
                      ['scope', 'codec', 'codec_name', 'images_sized', 'total_bytes', 'total_pixels', 'micro_bpp'])
            bar_figure(plt, full, 'micro_bpp', 'Compressed size (bits per pixel, log scale; lower is better)',
                       '%s: compressed size, %d maps (all codecs on the same maps)' % (s, full[0]['scope_images']),
                       res, stem, 'low')
            figs.append(('size', s, stem, part))
        else:
            notes.append(('figures', 'size figure for %s' % s, 'BDLC or competitors lack full size coverage'))
        # timing: same timed images for all plotted codecs
        timed_sets = {}
        for c in {r['codec'] for r in per}:
            timed_sets[c] = {i for i in mem[s] if (c, i) in by and by[(c, i)]['timed']}
        if not timed_sets.get(OURS):
            notes.append(('figures', 'speed figures for %s' % s, 'no timed BDLC measurements in this scope'))
            continue
        ref_ids = timed_sets[OURS]
        cods = sorted(c for c, ids in timed_sets.items() if ids == ref_ids)
        dropped = sorted(c for c in timed_sets if c not in cods)
        pts = []
        for c in cods:
            rs = [by[(c, i)] for i in ref_ids]
            N = sum(r['pixels'] for r in rs)
            pts.append({'scope': s, 'codec': c, 'codec_name': name(c), 'timed_images': len(rs), 'pixels': N,
                        'bytes': sum(r['bytes'] for r in rs), 'micro_bpp': 8 * sum(r['bytes'] for r in rs) / N,
                        'encode_s_sum': sum(r['encode_s'] for r in rs), 'decode_s_sum': sum(r['decode_s'] for r in rs),
                        'encode_MPix_s': N / sum(r['encode_s'] for r in rs) / 1e6,
                        'decode_MPix_s': N / sum(r['decode_s'] for r in rs) / 1e6})
        if len(pts) < 2:
            notes.append(('figures', 'speed figures for %s' % s, 'fewer than two codecs timed on the same maps'))
            continue
        fields = list(pts[0])
        n_t = len(ref_ids)
        for key, lab, word in (('encode_MPix_s', 'Encode throughput (MPix/s, log scale; higher is better)', 'encode'),
                               ('decode_MPix_s', 'Decode throughput (MPix/s, log scale; higher is better)', 'decode')):
            stem = '%s_speed_%s' % (word, tag)
            csv_write(os.path.join(res, 'plot_data', stem + '.csv'), pts, fields)
            bar_figure(plt, pts, key, lab, '%s: %s speed, %d timed maps, one CPU core' % (s, word, n_t), res, stem, 'high')
            figs.append((word, s, stem, dropped))
            stem = 'size_vs_%s_%s' % (word, tag)
            csv_write(os.path.join(res, 'plot_data', stem + '.csv'), pts, fields)
            scatter_figure(plt, pts, key, lab, '%s: size vs %s speed (same %d timed maps)' % (s, word, n_t), res, stem)
            figs.append(('size_vs_' + word, s, stem, dropped))
    return figs


# ------------------------------------------------------------------ paper tables
def tex_escape(s):
    return str(s).replace('\\', r'\textbackslash{}').replace('_', r'\_').replace('%', r'\%').replace('&', r'\&').replace('#', r'\#')


def write_table(res, stem, header, rows, caption):
    md = ['| ' + ' | '.join(header) + ' |', '|' + '|'.join('---' for _ in header) + '|']
    md += ['| ' + ' | '.join(str(x) for x in r) + ' |' for r in rows]
    with open(os.path.join(res, 'paper', 'tables', stem + '.md'), 'w', encoding='utf-8') as f:
        f.write('%s\n\n%s\n' % (caption, '\n'.join(md)))
    tex = [r'\begin{table}[t]', r'\centering', r'\caption{%s}' % tex_escape(caption),
           r'\begin{tabular}{l%s}' % ('r' * (len(header) - 1)), r'\hline',
           ' & '.join(tex_escape(h) for h in header) + r' \\', r'\hline']
    tex += [' & '.join(tex_escape(x) for x in r) + r' \\' for r in rows]
    tex += [r'\hline', r'\end{tabular}', r'\end{table}']
    with open(os.path.join(res, 'paper', 'tables', stem + '.tex'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(tex) + '\n')


def f4(x, nd=4):
    return '' if x is None or x == '' else ('%.*f' % (nd, x) if isinstance(x, float) else str(x))


def paper_tables(res, summary, pair, ptests):
    made = []
    for s in sorted({r['scope'] for r in summary}):
        rows = sorted([r for r in summary if r['scope'] == s], key=lambda r: r['micro_bpp'])
        tab = [[r['codec_name'], '%d/%d' % (r['images_sized'], r['scope_images']), f4(r['micro_bpp'], 5), f4(r['CR'], 1),
                '%d' % r['images_timed'], f4(r.get('encode_MPix_s'), 1), f4(r.get('decode_MPix_s'), 1)] for r in rows]
        stem = 'summary_%s' % safe(s)
        write_table(res, stem, ['Codec', 'Maps sized', 'bpp', 'CR', 'Maps timed', 'Encode MPix/s', 'Decode MPix/s'], tab,
                    '%s: size on all verified maps; speed on the timed maps (one pinned CPU core, median of repeats).' % s)
        made.append(stem)
        prs = sorted([p for p in pair if p['scope'] == s], key=lambda p: -p['size_gain_pct'])
        tab = [[p['reference_name'], p['n_common'], '%+.2f' % p['size_gain_pct'],
                '%d/%d/%d' % (p['size_wins'], p['size_ties'], p['size_losses']), p['n_timed_common'],
                f4(p.get('encode_speedup'), 2), f4(p.get('decode_speedup'), 2)] for p in prs]
        stem = 'comparison_%s' % safe(s)
        write_table(res, stem, ['Reference', 'Common maps', 'Size gain % (+ = BDLC smaller)', 'Maps W/T/L (size)',
                                'Common timed maps', 'Encode speedup', 'Decode speedup'], tab,
                    '%s: BDLC vs each configuration on the same maps. Negative size gain = BDLC larger (a loss); '
                    'speedup < 1 = BDLC slower.' % s)
        made.append(stem)
    if ptests:
        tab = [[t['scope'], t['hypothesis'], t['images'], t['groups'], t['groups_ours_better'],
                f4(t['estimate'], 2) if isinstance(t['estimate'], float) else (t['estimate'] or ''),
                ('[%s, %s]' % (f4(t.get('ci95_low'), 2), f4(t.get('ci95_high'), 2))) if t.get('ci95_low') is not None else '',
                f4(t.get('p_sign'), 4), f4(t.get('p_holm'), 4)] for t in ptests]
        write_table(res, 'protocol_B_tests', ['Scope', 'Hypothesis', 'Maps', 'Clusters', 'Clusters BDLC better',
                                              'Estimate', '95% CI', 'p (sign)', 'p (Holm)'], tab,
                    'Pre-registered hypotheses B1-B4 (PROTOKOL_B_UZ.md). delta_pct > 0 means BDLC smaller.')
        made.append('protocol_B_tests')
    return made


# ------------------------------------------------------------------ report text
def natijalar(res, status, proto, per, summary, pair, vbest, ptests, pareto, issues, notes):
    L = ['# Natijalar (avtomatik yaratilgan)', '',
         'Bu fayl `bench/make_reports.py` tomonidan faqat shu run’ning saqlangan o‘lchovlaridan yaratildi. '
         'Qo‘lda kiritilgan yoki taxminiy qiymat yo‘q.', '',
         '## Tajriba holati', '',
         '- Run holati (`status.json`): **%s**' % status.get('status'),
         '- Rejim: %s; kodeklar: %d; tasvirlar: %d; tezlik o‘lchangan tasvirlar: %s' % (
             status.get('mode', 'single-phase'), len(status.get('codecs', [])), status.get('images', 0),
             status.get('timing_images', status.get('images', 0))),
         '- Takrorlar (protokol): %s; o‘lchangan juftliklar: %s / %s; N/A: %s; xatolar: %s' % (
             proto.get('parameters', {}).get('repeats'), status.get('measured_pairs'), status.get('expected_pairs'),
             status.get('not_applicable_pairs', 0), status.get('failures')),
         '- Asosiy o‘lchovlar to‘plami: %d ta tekshirilgan (kodek, tasvir) juftligi; tezligi bilan: %d' % (
             len(per), sum(r['timed'] for r in per)),
         '- Platforma: %s; CPU: %s' % (proto.get('platform'), proto.get('cpu')), '']
    for s in sorted({r['scope'] for r in summary}):
        prs = [p for p in pair if p['scope'] == s]
        if not prs:
            continue
        L += ['## %s' % s, '']
        losses = sorted([p for p in prs if p['size_gain_pct'] < 0 and not is_ours_family(p['reference'])], key=lambda p: p['size_gain_pct'])
        wins = [p for p in prs if p['size_gain_pct'] > 0 and not is_ours_family(p['reference'])]
        L += ['### Hajm', '',
              '- BDLC %d ta raqib konfiguratsiyasidan kichik, **%d tasidan katta** (umumiy bayt, bir xil tasvirlar kesishmasida).' % (len(wins), len(losses))]
        for p in losses:
            L.append('  - **Yutqazish:** %s — BDLC %.2f%% katta; tasvirlar: %d kichik / %d teng / %d katta (kesishma %d/%d).' % (
                p['reference_name'], -p['size_gain_pct'], p['size_wins'], p['size_ties'], p['size_losses'], p['n_common'], p['scope_images']))
        best = sorted(wins, key=lambda p: p['size_gain_pct'])[:3]
        for p in best:
            L.append('  - Eng yaqin yutilgan raqib: %s — BDLC %.2f%% kichik (%d/%d tasvirda kichik).' % (
                p['reference_name'], p['size_gain_pct'], p['size_wins'], p['n_common']))
        for v in [v for v in vbest if v['scope'] == s]:
            L.append('  - Virtual eng yaxshi (%s, %d a’zo): Δ = %.2f%% (95%% CI %.2f … %.2f), %d/%d klasterda BDLC kichik.' % (
                v['oracle'], v['oracle_members'], v['delta_pct'], v['delta_ci95_low'] if v['delta_ci95_low'] is not None else float('nan'),
                v['delta_ci95_high'] if v['delta_ci95_high'] is not None else float('nan'), v['groups_ours_smaller'], v['groups']))
        for word, key in (('Siqish (encode) tezligi', 'encode_speedup'), ('Tiklash (decode) tezligi', 'decode_speedup')):
            tp = [p for p in prs if p.get(key) is not None and not is_ours_family(p['reference'])]
            L += ['', '### %s' % word, '']
            if not tp:
                L.append('- Tezlik o‘lchovi yo‘q (NOT_GENERATED).')
                continue
            slower = sorted([p for p in tp if p[key] < 1], key=lambda p: p[key])
            L.append('- BDLC %d ta raqibdan tezroq, **%d tasidan sekinroq** (bir xil tezlik o‘lchangan tasvirlarda).' % (
                len(tp) - len(slower), len(slower)))
            for p in slower:
                L.append('  - **Sekinroq:** %s — koeffitsiyent %.3f (kesishma %d tasvir).' % (p['reference_name'], p[key], p['n_timed_common']))
        L.append('')
    if ptests:
        L += ['## Oldindan e’lon qilingan gipotezalar (PROTOKOL_B_UZ.md)', '',
              '| Scope | Gipoteza | Klasterlar | Baho | 95% CI | p (sign) | p (Holm) |', '|---|---|---:|---|---|---:|---:|']
        for t in ptests:
            est = t['estimate'] if not isinstance(t['estimate'], float) else '%.2f' % t['estimate']
            ci = '%.2f … %.2f' % (t['ci95_low'], t['ci95_high']) if t.get('ci95_low') is not None else ''
            L.append('| %s | %s | %s | %s | %s | %s | %s |' % (t['scope'], t['hypothesis'], t['groups'], est or '', ci,
                                                              f4(t.get('p_sign'), 4), f4(t.get('p_holm'), 4)))
        dom = [p for p in pareto if p['bdlc_pareto_dominated_by_ref']]
        L += ['', '- B4 (Pareto): BDLC ni klasterlarning yarmidan ko‘pida hajmda ham, encode va decode’da ham ustun qilgan raqiblar: %s' % (
            ', '.join('%s (%s)' % (p['reference_name'], p['scope']) for p in dom) or 'yo‘q'), '']
    L += ['## Xatolar va qamrov', '', '- Batafsil: `reports/errors.md`. Asosiy to‘plamdan chiqarilgan yoki muammoli yozuvlar: %d.' % len(issues)]
    for folder, what, why in notes:
        L.append('- Yaratilmadi (%s): %s — %s' % (folder, what, why))
    with open(os.path.join(res, 'reports', 'NATIJALAR_UZ.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(L) + '\n')


def errors_md(res, run, issues, check_fail, notes):
    L = ['# Aniqlangan xatolar va muammolar', '']
    for fn, title in (('failures.json', 'Harness xatolari (failures.json)'), ('unavailable.json', 'Mavjud bo‘lmagan kodeklar'),
                      ('not_applicable.json', 'Qo‘llanmaydigan juftliklar (N/A)')):
        p = os.path.join(run, fn)
        items = jload(p) if os.path.exists(p) else None
        L += ['## ' + title, '']
        if items is None:
            L.append('- Fayl yo‘q (%s).' % fn)
        elif not items:
            L.append('- Yo‘q.')
        elif isinstance(items, dict):
            L += ['- %s: %s' % (k, v) for k, v in items.items()]
        else:
            L += ['- ' + json.dumps(x, ensure_ascii=False) for x in items[:500]]
            if len(items) > 500:
                L.append('- … jami %d ta' % len(items))
        L.append('')
    L += ['## Asosiy to‘plamni qurishda topilgan muammolar', '']
    L += ['- ' + json.dumps(x, ensure_ascii=False) for x in issues[:500]] or ['- Yo‘q.']
    L += ['', '## Hisobot tekshiruvidan o‘tmagan natijalar', '']
    L += ['- %s: %s' % (p, m) for p, m in check_fail] or ['- Yo‘q.']
    L += ['', '## Yaratilmagan natijalar (NOT_GENERATED)', '']
    L += ['- %s: %s — %s' % n for n in notes] or ['- Yo‘q.']
    with open(os.path.join(res, 'reports', 'errors.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(L) + '\n')


# ------------------------------------------------------------------ checks
def close(a, b):
    a, b = fnum(a), fnum(b)
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= TOL * max(1.0, abs(a), abs(b))


def check_file(path):
    """Readable and non-trivial; returns (ok, message)."""
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return False, 'missing or empty file'
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == '.csv':
            rows = csv_read(path)
            return (True, '%d data rows' % len(rows)) if rows else (False, 'CSV has only a header')
        if ext == '.json':
            jload(path)
            return True, 'JSON readable'
        if ext in ('.md', '.tex'):
            with open(path, encoding='utf-8') as f:
                return (True, 'text readable') if f.read().strip() else (False, 'empty text')
        if ext == '.png':
            from PIL import Image
            with Image.open(path) as im:
                dpi = im.info.get('dpi', (0, 0))
                im.verify()
            return (True, 'PNG, %.0f dpi' % dpi[0]) if dpi and dpi[0] >= 299.5 else (False, 'PNG below 300 dpi (%s)' % (dpi,))
        if ext == '.pdf':
            with open(path, 'rb') as f:
                return (True, 'PDF header ok') if f.read(5) == b'%PDF-' else (False, 'not a PDF')
        if ext == '.svg':
            with open(path, encoding='utf-8') as f:
                return (True, 'SVG ok') if '<svg' in f.read(4000) else (False, 'not an SVG')
    except Exception as ex:
        return False, '%s: %s' % (type(ex).__name__, ex)
    return True, 'exists'


def check_consistency(res, per, mem, proto):
    """Recompute key values from tables/per_image.csv and compare with every derived table."""
    fails = {}
    pi = csv_read(os.path.join(res, 'tables', 'per_image.csv'))
    rep = proto.get('parameters', {}).get('repeats')

    def bad(path, msg):
        fails.setdefault(path, []).append(msg)

    for r in pi:   # no zeros for missing values, formulas per row
        if not r['bytes'] or int(r['bytes']) <= 0:
            bad('tables/per_image.csv', 'non-positive bytes %s %s' % (r['codec'], r['input_id']))
        if not close(r['bpp'], 8 * int(r['bytes']) / int(r['pixels'])):
            bad('tables/per_image.csv', 'bpp formula %s %s' % (r['codec'], r['input_id']))
        if r['timed'] == 'True':
            if not (fnum(r['encode_s']) or 0) > 0 or not (fnum(r['decode_s']) or 0) > 0:
                bad('tables/per_image.csv', 'timed row without positive times %s %s' % (r['codec'], r['input_id']))
            if not close(r['encode_MPix_s'], int(r['pixels']) / float(r['encode_s']) / 1e6):
                bad('tables/per_image.csv', 'MPix/s formula %s %s' % (r['codec'], r['input_id']))
            if rep is not None and r['repeats'] != str(rep):
                bad('tables/per_image.csv', 'repeats %s != protocol %s (%s %s)' % (r['repeats'], rep, r['codec'], r['input_id']))
        elif any(r[k] not in ('', None) for k in ('encode_s', 'decode_s', 'encode_MPix_s', 'decode_MPix_s')):
            bad('tables/per_image.csv', 'untimed row carries a time value %s %s' % (r['codec'], r['input_id']))
    agg = {}
    for r in pi:
        for s, ids in mem.items():
            if r['input_id'] in ids:
                a = agg.setdefault((s, r['codec']), [0, 0, 0, 0, 0.0, 0.0])
                a[0] += 1
                a[1] += int(r['bytes'])
                a[2] += int(r['pixels'])
                if r['timed'] == 'True':
                    a[3] += int(r['pixels'])
                    a[4] += float(r['encode_s'])
                    a[5] += float(r['decode_s'])
    for r in csv_read(os.path.join(res, 'tables', 'summary_by_dataset.csv')):
        a = agg.get((r['scope'], r['codec']))
        p = 'tables/summary_by_dataset.csv'
        if a is None or int(r['images_sized']) != a[0] or int(r['total_bytes']) != a[1] or int(r['total_pixels']) != a[2]:
            bad(p, 'counts/bytes/pixels do not match per_image for %s %s' % (r['scope'], r['codec']))
            continue
        if not close(r['micro_bpp'], 8 * a[1] / a[2]) or not close(r['CR'], 16 / (8 * a[1] / a[2])):
            bad(p, 'bpp/CR formula %s %s' % (r['scope'], r['codec']))
        if a[3]:
            if not close(r['encode_MPix_s'], a[3] / a[4] / 1e6) or not close(r['decode_MPix_s'], a[3] / a[5] / 1e6):
                bad(p, 'throughput formula %s %s' % (r['scope'], r['codec']))
        elif r['encode_MPix_s'] not in ('', None):
            bad(p, 'speed given without timed maps %s %s' % (r['scope'], r['codec']))
    for r in csv_read(os.path.join(res, 'tables', 'pairwise_vs_bdlc.csv')):
        if not close(r['size_gain_pct'], 100 * (1 - int(r['sum_bytes_ours']) / int(r['sum_bytes_ref']))):
            bad('tables/pairwise_vs_bdlc.csv', 'size gain formula %s %s' % (r['scope'], r['reference']))
        if int(r['size_wins']) + int(r['size_ties']) + int(r['size_losses']) != int(r['n_common']):
            bad('tables/pairwise_vs_bdlc.csv', 'W/T/L do not add up %s %s' % (r['scope'], r['reference']))
    summ = {(r['scope'], r['codec']): r for r in csv_read(os.path.join(res, 'tables', 'summary_by_dataset.csv'))}
    for fn in os.listdir(os.path.join(res, 'plot_data')):
        if fn.startswith('size_') and not fn.startswith('size_vs_'):
            for r in csv_read(os.path.join(res, 'plot_data', fn)):
                s = summ.get((r['scope'], r['codec']))
                if s is None or not close(r['micro_bpp'], s['micro_bpp']):
                    bad('plot_data/' + fn, 'plotted bpp differs from summary for %s' % r['codec'])
        elif fn.endswith('.csv'):
            for r in csv_read(os.path.join(res, 'plot_data', fn)):
                if not close(r['encode_MPix_s'], int(r['pixels']) / float(r['encode_s_sum']) / 1e6) or \
                        not close(r['micro_bpp'], 8 * int(r['bytes']) / int(r['pixels'])):
                    bad('plot_data/' + fn, 'plotted value formula for %s' % r['codec'])
    return fails


# ------------------------------------------------------------------ main
def build(run, out=None):
    run = os.path.abspath(run)
    res = os.path.abspath(out or os.path.join(run, 'results'))
    tmp = res + '.tmp'
    shutil.rmtree(tmp, ignore_errors=True)
    for d in FOLDERS:
        os.makedirs(os.path.join(tmp, d))
    notes, manifest, check_fail = [], [], []
    started = time.strftime('%Y-%m-%d %H:%M:%S')
    try:
        status, proto, audit, per, issues, two = load_primary(run)
    except Exception as ex:
        status, proto, per, issues, two, audit = {}, {}, [], [{'issue': 'cannot read run: %s: %s' % (type(ex).__name__, ex)}], False, {}
    mem = scopes_of(audit) if audit else {}

    if not per:
        for d in FOLDERS:
            if d != 'reports':
                with open(os.path.join(tmp, d, 'NOT_GENERATED.md'), 'w', encoding='utf-8') as f:
                    f.write('# Yaratilmadi\n\nSabab: asosiy o‘lchovlar to‘plami bo‘sh (tekshirilgan (kodek, tasvir) juftligi yo‘q).\n'
                            'Yetishmagan ma’lumot: raw/ yoki raw_size/ va verification/ fayllari.\n')
        summary = pair = vbest = ptests = pareto = []
    else:
        T = os.path.join(tmp, 'tables')
        csv_write(os.path.join(T, 'per_image.csv'), per, list(per[0]))
        summary = summary_table(per, mem)
        csv_write(os.path.join(T, 'summary_by_dataset.csv'), summary, SUMMARY_FIELDS)
        pair = pairwise(per, mem)
        csv_write(os.path.join(T, 'pairwise_vs_bdlc.csv'), pair, PAIR_FIELDS)
        S = os.path.join(tmp, 'statistics')
        size, speed, wins, seq = stat_rows(per, mem, pair)
        csv_write(os.path.join(S, 'size_gain.csv'), size, list(size[0]) if size else ['scope'])
        timed_any = any(r['timed'] for r in per)
        if timed_any:
            sp = [r for r in speed if r.get('encode_speedup') is not None]
            csv_write(os.path.join(S, 'speed_coefficients.csv'), sp,
                      ['scope', 'reference', 'reference_name', 'n_timed_common', 'encode_speedup', 'decode_speedup', 'groups',
                       'groups_encode_faster', 'groups_decode_faster', 'sign_p_encode_faster', 'sign_p_decode_faster'])
        else:
            notes.append(('statistics', 'speed_coefficients.csv', 'no timed measurements in raw/'))
        csv_write(os.path.join(S, 'wins.csv'), wins, list(wins[0]) if wins else ['scope'])
        csv_write(os.path.join(S, 'sequence_level.csv'), seq,
                  ['scope', 'reference', 'group', 'images', 'bytes_ours', 'bytes_ref', 'size_gain_pct', 'timed_images',
                   'encode_speedup', 'decode_speedup'])
        vbest = virtual_best(per, mem)
        csv_write(os.path.join(S, 'virtual_best.csv'), vbest, list(vbest[0]) if vbest else ['scope'])
        ptests, pareto = protocol_B(per, mem, pair)
        if ptests:
            csv_write(os.path.join(S, 'protocol_B_tests.csv'), ptests,
                      ['scope', 'hypothesis', 'images', 'groups', 'groups_ours_better', 'statistic', 'estimate',
                       'ci95_low', 'ci95_high', 'p_sign', 'p_wilcoxon', 'p_holm'])
            csv_write(os.path.join(S, 'pareto_B4.csv'), pareto, list(pareto[0]) if pareto else ['scope'])
        cold = []
        for c in status.get('codecs', []):
            p = os.path.join(run, 'coldstart', c + '.json')
            if os.path.exists(p):
                rs = jload(p)
                for mode in sorted({r.get('cache_mode') for r in rs}):
                    rr = [r for r in rs if r.get('cache_mode') == mode and r.get('ok')]
                    if rr:
                        cold.append({'codec': c, 'codec_name': name(c), 'numba_cache': mode, 'runs': len(rr),
                                     **{k.replace('_ns', '_ms'): float(np.median([r[k] for r in rr])) / 1e6
                                        for k in ('import_ns', 'first_encode_ns', 'first_decode_ns', 'second_encode_ns', 'second_decode_ns')}})
        if cold:
            csv_write(os.path.join(S, 'coldstart.csv'), cold, list(cold[0]))
        else:
            notes.append(('statistics', 'coldstart.csv', 'no successful cold-start measurement in coldstart/'))
        figs = make_figures(tmp, per, mem, summary, notes)
        paper_tables(tmp, summary, pair, ptests)
        with open(os.path.join(tmp, 'paper', 'figures', 'CAPTIONS.md'), 'w', encoding='utf-8') as f:
            f.write('# Figure captions\n\n')
            for kind, s, stem, excluded in figs:
                f.write('- `%s` (%s, %s): values from `plot_data/%s.csv`. Size is the counted stream size in bits per pixel; '
                        'speed is megapixels per second of net single-core time (median of the protocol repeats). '
                        'All codecs in a figure are measured on the same maps.%s%s\n' % (
                            stem, kind, s, stem,
                            ' BDLC ablation variants are shown only in the bar charts.' if kind.startswith('size_vs') else '',
                            (' Not shown (incomplete coverage on these maps): %s.' % ', '.join(excluded)) if excluded else ''))
        natijalar(tmp, status, proto, per, summary, pair, vbest, ptests, pareto, issues, notes)

    # NOT_GENERATED notes and empty folders
    for folder in FOLDERS:
        fl = [n for n in notes if n[0] == folder]
        if folder == 'reports':
            continue
        path = os.path.join(tmp, folder)
        if fl or not os.listdir(path):
            with open(os.path.join(path, 'NOT_GENERATED.md'), 'a', encoding='utf-8') as f:
                f.write('# Yaratilmagan natijalar\n\n')
                for _, what, why in fl:
                    f.write('- **%s** — sabab: %s.\n' % (what, why))
                if not fl:
                    f.write('- Bu papka uchun hech qanday natija yaratilmadi (yetishmagan ma’lumot: asosiy o‘lchovlar).\n')

    # checks
    fails = check_consistency(tmp, per, mem, proto) if per else {}
    for dp, _, fs in os.walk(tmp):
        for fn in sorted(fs):
            full = os.path.join(dp, fn)
            rel = os.path.relpath(full, tmp).replace(os.sep, '/')
            if rel.startswith('reports/'):
                continue
            if fn == 'NOT_GENERATED.md':
                manifest.append({'path': rel, 'kind': 'not_generated_note', 'status': 'not_generated', 'checks': 'explains a missing result', 'ok': False})
                continue
            ok, msg = check_file(full)
            extra = fails.get(rel, [])
            if extra:
                ok, msg = False, msg + '; consistency: ' + '; '.join(extra[:5])
            manifest.append({'path': rel, 'kind': os.path.splitext(fn)[1][1:], 'status': 'generated', 'checks': msg, 'ok': ok})
            if not ok:
                check_fail.append((rel, msg))
    for rel in ('tables/per_image.csv', 'tables/summary_by_dataset.csv', 'tables/pairwise_vs_bdlc.csv'):
        if not any(m['path'] == rel for m in manifest):
            manifest.append({'path': rel, 'kind': 'csv', 'status': 'not_generated', 'checks': 'required table missing', 'ok': False})
            check_fail.append((rel, 'required table missing'))
    errors_md(tmp, run, issues, check_fail, notes)
    core_ok = all(m['ok'] for m in manifest if m['path'] in ('tables/per_image.csv', 'tables/summary_by_dataset.csv', 'tables/pairwise_vs_bdlc.csv'))
    rstatus = 'FAILED' if not per or not core_ok else ('COMPLETE' if all(m['ok'] for m in manifest) and not notes else 'PARTIAL')
    for rel in ('reports/NATIJALAR_UZ.md', 'reports/errors.md'):
        ok, msg = check_file(os.path.join(tmp, rel))
        manifest.append({'path': rel, 'kind': 'md', 'status': 'generated' if ok else 'not_generated', 'checks': msg, 'ok': ok})
        if not ok:
            rstatus = 'PARTIAL' if rstatus == 'COMPLETE' else rstatus
    manifest.append({'path': 'reports/status.json', 'kind': 'json', 'status': 'generated', 'checks': 'JSON readable', 'ok': True})
    rep_status = {'experiment_status': status.get('status'), 'experiment_status_file': 'status.json (run root, never modified)',
                  'reporting_status': rstatus, 'generated_at': started, 'run': run, 'results_dir': res,
                  'primary_pairs': len(per), 'timed_pairs': sum(r['timed'] for r in per), 'two_phase_run': two,
                  'artifacts': len(manifest), 'artifacts_failed': sum(not m['ok'] for m in manifest),
                  'not_generated': ['%s: %s' % (n[0], n[1]) for n in notes]}
    with open(os.path.join(tmp, 'reports', 'status.json'), 'w', encoding='utf-8') as f:
        json.dump(rep_status, f, indent=1, ensure_ascii=False)
    with open(os.path.join(tmp, 'reports', 'artifact_manifest.json'), 'w', encoding='utf-8') as f:
        json.dump({'reporting_status': rstatus, 'experiment_status': status.get('status'), 'generated_at': started,
                   'artifacts': manifest}, f, indent=1, ensure_ascii=False)
    shutil.rmtree(res, ignore_errors=True)
    os.replace(tmp, res)
    print('results:', res, '| reporting_status:', rstatus, '| artifacts:', len(manifest),
          '| failed checks:', len(check_fail), '| not generated:', len(notes))
    return rstatus


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('run')
    ap.add_argument('--out', help='output folder (default RUN/results)')
    a = ap.parse_args()
    build(a.run, a.out)
