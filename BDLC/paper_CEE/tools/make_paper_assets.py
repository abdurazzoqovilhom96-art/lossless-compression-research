"""Builds every number, table and figure of the C&EE manuscript from the measured files of runs B and C.

    python -I paper_CEE/tools/make_paper_assets.py

Reads  BDLC/runs/20261029_081034_test_B/  and  BDLC/runs/20261030_134701_test_C/  (results/, byte_breakdown.csv,
status files), BDLC/protocol_B.json, BDLC/protocol_C.json, the input maps of protocol C (class count only), the
post-hoc I/O calibration run and the published ECC-2026 values in tools/published_ecc2026.json. Writes
    paper_CEE/overleaf/numbers.tex        one \\newcommand per number used in the text
    paper_CEE/overleaf/tables/*.tex       journal-format tables (booktabs, no vertical rules)
    paper_CEE/overleaf/figures/*.pdf      vector figures, one figure per file, no in-figure title
    paper_CEE/overleaf/submission/graphical_abstract.png
    paper_CEE/tools/assets_manifest.json  every output with the source files it was computed from
No number is typed by hand; nothing is estimated or filled in.
"""
import csv
import json
import math
import os
import re
import statistics
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
BDLC = os.path.dirname(os.path.dirname(HERE))
RUN = os.path.join(BDLC, 'runs', '20261029_081034_test_B')
RES = os.path.join(RUN, 'results')
# BDLC_PAPER_OUT / BDLC_PAPER_LANG=uz: build the same assets elsewhere with Uzbek figure labels (the authors'
# Uzbek reading copy, paper_CEE/uzbek). Without them the script writes the manuscript assets into overleaf/.
OUT = os.environ.get('BDLC_PAPER_OUT') or os.path.join(os.path.dirname(HERE), 'overleaf')
LANG = os.environ.get('BDLC_PAPER_LANG', 'en')
assert LANG in ('en', 'uz'), LANG
TAB = os.path.join(OUT, 'tables')
FIG = os.path.join(OUT, 'figures')
SUB = os.path.join(OUT, 'submission')
for d in (TAB, FIG, SUB):
    os.makedirs(d, exist_ok=True)

MANIFEST = []          # (output, [sources])
MACROS = []            # (name, value, source)

DAVIS = 'DAVIS2017_480p'
CTC = ['Fluo-N2DH-GOWT1_GT_SEG', 'PhC-C2DL-PSC_GT_SEG', 'Fluo-N2DH-SIM+_GT_SEG']
SCOPE_NAME = {'DAVIS2017_480p': 'DAVIS 2017', 'ALL_REAL': 'All real maps',
              'Fluo-N2DH-GOWT1_GT_SEG': 'Fluo-N2DH-GOWT1', 'PhC-C2DL-PSC_GT_SEG': 'PhC-C2DL-PSC',
              'Fluo-N2DH-SIM+_GT_SEG': 'Fluo-N2DH-SIM+ (simulated)'}
VARIANTS = ['bdlc_crc', 'bdlc_uniform', 'bdlc_noslope', 'bdlc_nok2', 'bdlc_nopass']
SEG = {'crackle_mo0', 'crackle_mo3', 'crackle_mo0_zstd19', 'crackle_mo3_zstd19', 'cseg_gzip9', 'compresso'}
ECC = {'ecc_direct', 'ecc_pi'}
GENERAL = {'zlib9', 'lzma9e', 'zstd3', 'zstd19', 'brotli11', 'bz2_9', 'blosc2_zstd_bitshuffle',
           'palette_zstd19', 'palette_lzma9e'}
STANDARD = {'png16', 'jpegls', 'jpegxl7', 'jpegxl9', 'jpegxl10', 'jpeg2k', 'htj2k', 'lerc', 'lerc_zstd',
            'hevc_scc_pi', 'hevc_scc_direct', 'jbig_gray_pi', 'jbig_binary_pi', 'flif_u16_e60',
            'flif_u16_e100', 'flif_pi_e60', 'flif_pi_e100'}
LEGACY = {'rvc'}


def category(c):
    if c == 'bdlc':
        return 'BDLC'
    if c in ECC:
        return 'ECC-2026'
    if c in SEG:
        return 'Segmentation codecs'
    if c in STANDARD:
        return 'Image and video codecs'
    if c in GENERAL:
        return 'General-purpose compressors'
    if c in LEGACY:
        return 'Earlier codec (RVC)'
    if c in VARIANTS:
        return 'BDLC variant'
    raise KeyError(c)


def rel(p):
    return os.path.relpath(p, BDLC).replace('\\', '/')


def read_csv(path):
    with open(path, encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def tex(s):
    return (str(s).replace('\\', r'\textbackslash{}').replace('&', r'\&').replace('%', r'\%')
            .replace('_', r'\_').replace('#', r'\#').replace('$', r'\$').replace('~', r'\textasciitilde{}'))


def fint(n):
    return '{:,}'.format(int(n)).replace(',', '{,}')


def fmag(x):
    """Speed-ups and throughputs: three significant figures, never rounded to 0 or 1."""
    x = float(x)
    if x >= 100:
        return fnum(x, 0)
    if x >= 10:
        return fnum(x, 1)
    if x >= 1:
        return fnum(x, 2)
    return fnum(x, 2) if x >= 0.1 else '%.2g' % x


def fnum(x, nd):
    """Fixed decimals; thousands separated by a comma ({,} so that LaTeX adds no space), as in the text."""
    s = '{:,.{}f}'.format(x, nd).replace(',', '{,}')
    return s.replace('-', '\\textminus ', 1) if s.startswith('-') else s


def andjoin(names):
    """English list: 'A', 'A and B', 'A, B and C'."""
    names = list(names)
    return names[0] if len(names) == 1 else ', '.join(names[:-1]) + ' and ' + names[-1]


def fp(p, approx_floor=False):
    """p-value for LaTeX. Normal-approximation p-values below 1e-15 are at the limit of double precision
    (Linux gives 2.2e-16, Windows 0) and are written as < 10^-15."""
    p = float(p)
    if approx_floor and p < 1e-15:
        return r'$<10^{-15}$'
    if p >= 0.001:
        return '%.3f' % p
    e = int(math.floor(math.log10(p)))
    m = p / 10 ** e
    if round(m, 1) >= 10:
        m, e = m / 10, e + 1
    return r'$%.1f\times10^{%d}$' % (m, e)


def macro(name, value, source):
    assert name.isalpha(), name
    MACROS.append((name, value, source))


# ---------------------------------------------------------------- load
P_SUMMARY = os.path.join(RES, 'tables', 'summary_by_dataset.csv')
P_PAIR = os.path.join(RES, 'tables', 'pairwise_vs_bdlc.csv')
P_TESTS = os.path.join(RES, 'statistics', 'protocol_B_tests.csv')
P_PARETO = os.path.join(RES, 'statistics', 'pareto_B4.csv')
P_SIZEG = os.path.join(RES, 'statistics', 'size_gain.csv')
P_SPEED = os.path.join(RES, 'statistics', 'speed_coefficients.csv')
P_VB = os.path.join(RES, 'statistics', 'virtual_best.csv')
P_COLD = os.path.join(RES, 'statistics', 'coldstart.csv')
P_BB = os.path.join(RUN, 'byte_breakdown.csv')
P_STATUS = os.path.join(RUN, 'status.json')
P_REPST = os.path.join(RES, 'reports', 'status.json')
P_PROTO = os.path.join(BDLC, 'protocol_B.json')
P_FAIL = os.path.join(RUN, 'failures.json')
P_NA = os.path.join(RUN, 'not_applicable.json')

summary = read_csv(P_SUMMARY)
S = {(r['scope'], r['codec']): r for r in summary}
pair = {(r['scope'], r['reference']): r for r in read_csv(P_PAIR)}
tests = read_csv(P_TESTS)
pareto = read_csv(P_PARETO)
sizeg = {(r['scope'], r['reference']): r for r in read_csv(P_SIZEG)}
speed = {(r['scope'], r['reference']): r for r in read_csv(P_SPEED)}
vb = {(r['scope'], r['oracle']): r for r in read_csv(P_VB)}
cold = read_csv(P_COLD)
bb = read_csv(P_BB)
status = json.load(open(P_STATUS, encoding='utf-8'))
repst = json.load(open(P_REPST, encoding='utf-8'))
proto = json.load(open(P_PROTO, encoding='utf-8'))
failures = json.load(open(P_FAIL, encoding='utf-8'))
not_app = json.load(open(P_NA, encoding='utf-8'))

codecs = list(proto['codecs'].keys())
competitors = [c for c in codecs if c != 'bdlc' and c not in VARIANTS]
assert len(codecs) == 41 and len(competitors) == 35, (len(codecs), len(competitors))
NAME = {r['codec']: r['codec_name'] for r in summary}
NAME['bdlc'] = 'BDLC'

# ---------------------------------------------------------------- run-level numbers
macro('Nconfigs', str(len(codecs)), rel(P_PROTO))
macro('Ncompetitors', str(len(competitors)), rel(P_PROTO))
macro('NnonECC', str(len([c for c in competitors if c not in ECC])), rel(P_PROTO))
macro('Nvariants', str(len(VARIANTS)), rel(P_PROTO))
macro('NmapsTotal', fint(len(proto['inputs'])), rel(P_PROTO))
macro('NtimedTotal', fint(proto['parameters']['timing_images']), rel(P_PROTO))
macro('Nrepeats', str(proto['parameters']['repeats']), rel(P_PROTO))
macro('NsizeJobs', str(proto['parameters']['size_jobs']), rel(P_PROTO))
macro('Ncoldruns', str(proto['parameters']['coldstart_runs']), rel(P_PROTO))
macro('NprimaryPairs', fint(repst['primary_pairs']), rel(P_REPST))
macro('NtimedPairs', fint(repst['timed_pairs']), rel(P_REPST))
macro('NreportFiles', str(repst['artifacts']), rel(P_REPST))
assert status['status'] == 'COMPLETE' and status['failures'] == 0 and failures == [] and not_app == []
macro('Nfailures', str(len(failures)), rel(P_FAIL))
macro('NnotApplicable', str(len(not_app)), rel(P_NA))
macro('ProtocolHash', proto_hash := '96e16ed1', 'SHA-256 of BDLC/protocol_B.json (first 8 hex digits)')
macro('CPUname', tex(proto['cpu'].replace('13th Gen ', '').replace('(R)', '').replace('(TM)', '')), rel(P_PROTO))
macro('PythonVersion', proto['python'].split()[0], rel(P_PROTO))
pk = dict(x.split('==') for x in proto['packages'])
for key, name in (('numba', 'VerNumba'), ('numpy', 'VerNumpy'), ('imagecodecs', 'VerImagecodecs'),
                  ('crackle-codec', 'VerCrackle'), ('compressed_segmentation', 'VerCseg'),
                  ('zstandard', 'VerZstandard')):
    macro(name, pk[key], rel(P_PROTO))

# check the protocol hash literally (the macro above must match the file)
import hashlib
with open(P_PROTO, 'rb') as f:
    h = hashlib.sha256(f.read()).hexdigest()
assert h.startswith(proto_hash), h

# per-scope map counts, clusters and timed maps (BDLC rows of the summary)
for scope, tag in ((DAVIS, 'DAVIS'), ('ALL_REAL', 'Real'), ('Fluo-N2DH-GOWT1_GT_SEG', 'GOWT'),
                   ('PhC-C2DL-PSC_GT_SEG', 'PSC'), ('Fluo-N2DH-SIM+_GT_SEG', 'SIM')):
    r = S[(scope, 'bdlc')]
    macro('Nmaps' + tag, fint(r['images_sized']), rel(P_SUMMARY))
    macro('Ntimed' + tag, fint(r['images_timed']), rel(P_SUMMARY))
    macro('EncMPix' + tag, fnum(float(r['encode_MPix_s']), 0), rel(P_SUMMARY))
    macro('DecMPix' + tag, fnum(float(r['decode_MPix_s']), 0), rel(P_SUMMARY))
    macro('Bpp' + tag, '%.5f' % float(r['micro_bpp']), rel(P_SUMMARY))
n_ctc = sum(int(S[(s, 'bdlc')]['images_sized']) for s in CTC)
assert n_ctc + int(S[(DAVIS, 'bdlc')]['images_sized']) == len(proto['inputs'])
macro('NmapsCTC', fint(n_ctc), rel(P_SUMMARY))
seqs = {}
for row in bb:
    seqs.setdefault(row['dataset'], set()).add(row['group'])
macro('NseqDAVIS', str(len(seqs[DAVIS])), rel(P_BB))
macro('NseqReal', str(sum(len(seqs[s]) for s in seqs if 'SIM' not in s)), rel(P_BB))

# development maps (used for the design and table T1; excluded from the test data)
P_DEV = os.path.join(os.path.dirname(BDLC), 'real_manifest.csv')
dev = read_csv(P_DEV)
macro('NdevMaps', str(len(dev)), rel(P_DEV))
macro('NdevHeLa', str(sum(r['dataset'].startswith('DIC-C2DH-HeLa') for r in dev)), rel(P_DEV))
macro('NdevUThree', str(sum(r['dataset'].startswith('PhC-C2DH-U373') for r in dev)), rel(P_DEV))
macro('NdevSeq', str(len({r['group'] for r in dev})), rel(P_DEV))
assert all(r['split'] == 'development' for r in dev)

# ---------------------------------------------------------------- pre-registered tests (B1-B4)
T = {(r['scope'], r['hypothesis'][:2]): r for r in tests}
for scope, tag in ((DAVIS, 'DAVIS'), ('ALL_REAL', 'Real')):
    b1, b2, b3 = T[(scope, 'B1')], T[(scope, 'B2')], T[(scope, 'B3')]
    macro('BoneDelta' + tag, fnum(float(b1['estimate']), 1), rel(P_TESTS))
    macro('BoneDeltaAbs' + tag, fnum(abs(float(b1['estimate'])), 1), rel(P_TESTS))
    macro('BoneLo' + tag, fnum(float(b1['ci95_low']), 1), rel(P_TESTS))
    macro('BoneHi' + tag, fnum(float(b1['ci95_high']), 1), rel(P_TESTS))
    macro('BoneLoAbs' + tag, fnum(abs(float(b1['ci95_high'])), 1), rel(P_TESTS))
    macro('BoneHiAbs' + tag, fnum(abs(float(b1['ci95_low'])), 1), rel(P_TESTS))
    macro('BoneBetter' + tag, b1['groups_ours_better'], rel(P_TESTS))
    macro('BoneGroups' + tag, b1['groups'], rel(P_TESTS))
    macro('BonePsign' + tag, fp(b1['p_sign']), rel(P_TESTS))
    macro('BonePholm' + tag, fp(b1['p_holm']), rel(P_TESTS))
    macro('BoneWilcoxon' + tag, fp(b1['p_wilcoxon'], approx_floor=True), rel(P_TESTS))
    macro('BtwoWilcoxon' + tag, fp(b2['p_wilcoxon'], approx_floor=True), rel(P_TESTS))
    macro('BtwoDelta' + tag, fnum(float(b2['estimate']), 1), rel(P_TESTS))
    macro('BtwoLo' + tag, fnum(float(b2['ci95_low']), 1), rel(P_TESTS))
    macro('BtwoHi' + tag, fnum(float(b2['ci95_high']), 1), rel(P_TESTS))
    macro('BtwoBetter' + tag, b2['groups_ours_better'], rel(P_TESTS))
    macro('BtwoPsign' + tag, fp(b2['p_sign']), rel(P_TESTS))
    macro('BtwoPholm' + tag, fp(b2['p_holm']), rel(P_TESTS))
    enc, dec = [float(x) for x in b3['estimate'].split('/')]
    macro('BthreeEnc' + tag, fnum(enc, 1), rel(P_TESTS))
    macro('BthreeDec' + tag, fnum(dec, 1), rel(P_TESTS))
    ge, gd = [x.strip().split()[0] for x in b3['groups_ours_better'].split('/')]
    macro('BthreeEncGroups' + tag, ge, rel(P_TESTS))
    macro('BthreeDecGroups' + tag, gd, rel(P_TESTS))
    macro('BthreePsign' + tag, fp(b3['p_sign']), rel(P_TESTS))
    macro('BthreePholm' + tag, fp(b3['p_holm']), rel(P_TESTS))
    dom = [r for r in pareto if r['scope'] == scope and r['bdlc_pareto_dominated_by_ref'] == 'True']
    nref = len([r for r in pareto if r['scope'] == scope])
    assert nref == 35
    macro('BfourDominating' + tag, str(len(dom)), rel(P_PARETO))
    macro('BfourMaxGroups' + tag, str(max(int(r['groups_ref_smaller_and_faster_both']) for r in pareto
                                          if r['scope'] == scope)), rel(P_PARETO))

# sequences in which BDLC beat the ECC oracle (names come from the per-cluster column)
cl = vb[(DAVIS, 'ECC_only')]
col = 'group_log_ratios'
pairs_ = [x.split('=') for x in cl[col].split(';')]
better = sorted(name.split('/')[-1] for name, d in pairs_ if float(d) < 0)
assert str(len(better)) == T[(DAVIS, 'B1')]['groups_ours_better']
macro('BoneBetterNames', ' and '.join(r'\textit{%s}' % tex(b) for b in better), rel(P_VB))

# ---------------------------------------------------------------- pooled comparisons (DAVIS)
def pooled_gain(scope, c):
    return float(pair[(scope, c)]['size_gain_pct'])


for c, tag in (('ecc_direct', 'ECC'), ('ecc_pi', 'ECCpi'), ('crackle_mo0_zstd19', 'Crackle'),
               ('jpegls', 'JPEGLS'), ('zstd3', 'Zstdthree'), ('zstd19', 'Zstdnineteen'),
               ('jpegxl10', 'JXLten'), ('hevc_scc_direct', 'HEVC'), ('flif_u16_e100', 'FLIF'),
               ('compresso', 'Compresso'), ('jbig_binary_pi', 'JBIG')):
    g = pooled_gain(DAVIS, c)
    sp = pair[(DAVIS, c)]
    macro('Gain' + tag, fnum(g, 1), rel(P_PAIR))
    macro('GainAbs' + tag, fnum(abs(g), 1), rel(P_PAIR))
    macro('Enc' + tag, fmag(sp['encode_speedup']), rel(P_PAIR))
    macro('Dec' + tag, fmag(sp['decode_speedup']), rel(P_PAIR))
    macro('Bpp' + tag, '%.5f' % float(S[(DAVIS, c)]['micro_bpp']), rel(P_SUMMARY))
    macro('EncMPix' + tag, fmag(S[(DAVIS, c)]['encode_MPix_s']), rel(P_SUMMARY))
    macro('DecMPix' + tag, fmag(S[(DAVIS, c)]['decode_MPix_s']), rel(P_SUMMARY))
    macro('SizeLoss' + tag, fint(sp['size_losses']), rel(P_PAIR))
    macro('SizeWin' + tag, fint(sp['size_wins']), rel(P_PAIR))

# counts over the 35 competitors on DAVIS (pooled size, ratio-of-sums speed)
won_size = [c for c in competitors if float(pair[(DAVIS, c)]['size_gain_pct']) > 0]
won_enc = [c for c in competitors if float(pair[(DAVIS, c)]['encode_speedup']) > 1]
won_dec = [c for c in competitors if float(pair[(DAVIS, c)]['decode_speedup']) > 1]
won_all = [c for c in competitors if c in won_size and c in won_enc and c in won_dec]
macro('NwonSize', str(len(won_size)), rel(P_PAIR))
macro('NwonEnc', str(len(won_enc)), rel(P_PAIR))
macro('NwonDec', str(len(won_dec)), rel(P_PAIR))
macro('NwonAll', str(len(won_all)), rel(P_PAIR))
macro('LostSizeNames', andjoin(tex(NAME[c]) for c in competitors if c not in won_size), rel(P_PAIR))
macro('LostEncNames', andjoin(tex(NAME[c]) for c in competitors if c not in won_enc), rel(P_PAIR))
macro('LostDecNames', andjoin(tex(NAME[c]) for c in competitors if c not in won_dec), rel(P_PAIR))
# best non-ECC configuration by pooled size
best_non_ecc = min((c for c in competitors if c not in ECC), key=lambda c: float(S[(DAVIS, c)]['micro_bpp']))
macro('BestNonECCName', tex(NAME[best_non_ecc]), rel(P_SUMMARY))
macro('GainBestNonECC', fnum(pooled_gain(DAVIS, best_non_ecc), 1), rel(P_PAIR))
macro('EncBestNonECC', fnum(float(pair[(DAVIS, best_non_ecc)]['encode_speedup']), 1), rel(P_PAIR))
macro('DecBestNonECC', fnum(float(pair[(DAVIS, best_non_ecc)]['decode_speedup']), 1), rel(P_PAIR))
# size ratio of the fast codecs to BDLC
for c, tag in (('jpegls', 'JPEGLS'), ('zstd3', 'Zstdthree'), ('zstd19', 'Zstdnineteen')):
    macro('Ratio' + tag, fnum(float(S[(DAVIS, c)]['micro_bpp']) / float(S[(DAVIS, 'bdlc')]['micro_bpp']), 1), rel(P_SUMMARY))

# ---------------------------------------------------------------- ablation
for c, tag in (('bdlc_nok2', 'NoKtwo'), ('bdlc_noslope', 'NoSlope'), ('bdlc_nopass', 'NoPass'),
               ('bdlc_uniform', 'Uniform'), ('bdlc_crc', 'CRC')):
    a, b = float(S[(DAVIS, c)]['total_bytes']), float(S[(DAVIS, 'bdlc')]['total_bytes'])
    macro('Abl' + tag, fnum(100 * (a / b - 1), 1), rel(P_SUMMARY))       # % larger than BDLC
    for scope, t2 in (('Fluo-N2DH-GOWT1_GT_SEG', 'GOWT'), ('PhC-C2DL-PSC_GT_SEG', 'PSC')):
        a2, b2 = float(S[(scope, c)]['total_bytes']), float(S[(scope, 'bdlc')]['total_bytes'])
        macro('Abl' + tag + t2, fnum(100 * (a2 / b2 - 1), 1), rel(P_SUMMARY))

# ---------------------------------------------------------------- cold start
cs = {(r['codec'], r['numba_cache']): r for r in cold}
for mode, tag in (('cache', 'Cache'), ('nocache', 'NoCache')):
    r = cs[('bdlc', mode)]
    macro('ColdImport' + tag, fnum(float(r['import_ms']), 0), rel(P_COLD))
    macro('ColdEnc' + tag, fnum(float(r['first_encode_ms']), 0), rel(P_COLD))
    macro('ColdDec' + tag, fnum(float(r['first_decode_ms']), 0), rel(P_COLD))
    macro('WarmEnc' + tag, fnum(float(r['second_encode_ms']), 2), rel(P_COLD))
    macro('WarmDec' + tag, fnum(float(r['second_decode_ms']), 2), rel(P_COLD))
macro('ColdEncNoCacheS', fnum(float(cs[('bdlc', 'nocache')]['first_encode_ms']) / 1000, 1), rel(P_COLD))
macro('ColdDecNoCacheS', fnum(float(cs[('bdlc', 'nocache')]['first_decode_ms']) / 1000, 1), rel(P_COLD))

# ---------------------------------------------------------------- coding bound check and bit shares
# over the maps of both runs (protocol B and protocol C)
P_BB_BOTH = [P_BB, os.path.join(BDLC, 'runs', '20261030_134701_test_C', 'byte_breakdown.csv')]
bb_both = bb + read_csv(P_BB_BOTH[1])
pm = [float(r['payload_minus_model_bytes']) for r in bb_both]
macro('NbbMaps', fint(len(bb_both)), ' + '.join(rel(p) for p in P_BB_BOTH))
macro('BoundMin', fnum(min(pm), 2), ' + '.join(rel(p) for p in P_BB_BOTH))
macro('BoundMax', fnum(max(pm), 2), ' + '.join(rel(p) for p in P_BB_BOTH))
unattr = max(abs(float(r['unattributed_bits'])) for r in bb_both)
macro('UnattributedMax', ('%.1g' % unattr) if unattr else '0', ' + '.join(rel(p) for p in P_BB_BOTH))
COMP = [('Label', ['label_set_bits', 'label_above_k1_bits', 'label_nextrun_k2_bits', 'label_escape_bits']),
        ('Run-end mode (PASS / V)', ['mode_vertical_pass_bits']),
        ('Displacement', ['displacement_bits']),
        ('Horizontal jump', ['horizontal_jump_bits']),
        ('Run length (new object, no reference)', ['newobject_length_bits', 'noref_end_length_bits'])]
shares = {}
for ds in [DAVIS] + CTC:
    rows = [r for r in bb if r['dataset'] == ds]
    tot = sum(float(r['model_bits_total']) for r in rows)
    parts = [sum(float(r[k]) for r in rows for k in ks) for _, ks in COMP]
    assert abs(sum(parts) - tot) <= 1e-6 * tot + 1, (ds, sum(parts), tot)
    shares[ds] = [100 * p / tot for p in parts]
macro('ShareDispDAVIS', fnum(shares[DAVIS][2], 0), rel(P_BB))
macro('ShareRunEndDAVIS', fnum(sum(shares[DAVIS][1:4]), 0), rel(P_BB))   # mode + displacement + horizontal jump
macro('ShareRunLenDAVIS', fnum(shares[DAVIS][4], 0), rel(P_BB))           # run lengths of new objects / no reference
macro('ShareLabelDAVIS', fnum(shares[DAVIS][0], 0), rel(P_BB))
# K statistics
for ds, tag in ((DAVIS, 'DAVIS'), ('Fluo-N2DH-GOWT1_GT_SEG', 'GOWT'), ('PhC-C2DL-PSC_GT_SEG', 'PSC'),
                ('Fluo-N2DH-SIM+_GT_SEG', 'SIM')):
    ks = [int(r['K']) for r in bb if r['dataset'] == ds]
    macro('Kmin' + tag, str(min(ks)), rel(P_BB))
    macro('Kmed' + tag, ('%g' % statistics.median(ks)), rel(P_BB))
    macro('Kmax' + tag, str(max(ks)), rel(P_BB))

# ---------------------------------------------------------------- S0 sensitivity analysis (PROTOKOL_B_UZ.md, section 3)
# Pre-registered secondary analysis: the label set is not charged to anybody, i.e. sigma = 0 for the rank-map
# configurations and BDLC's own label-set bits (analyze(): label_set_bits) are subtracted. Computed here with the
# run's own sign test, bootstrap and Delta functions (bench/make_reports.py) from the measured per-map sizes.
from collections import defaultdict
sys.path.insert(0, os.path.join(BDLC, 'bench'))
import make_reports as MR            # noqa: E402  (same statistics code as the run's reports)
from external import sigma_star      # noqa: E402  (exact label-set block size of the rank-map configurations)
P_PER = os.path.join(RES, 'tables', 'per_image.csv')
pi_cfg = sorted(c for c, v in proto['codecs'].items() if 'sigma*(K)' in v[2])
lsb = {r['input_id']: float(r['label_set_bits']) for r in bb}
prim, s0, grp = defaultdict(dict), defaultdict(dict), {}
ecc_t = {'null_e': [], 'null_d': [], 'net_e': [], 'net_d': []}
sig_davis = []
with open(P_PER, encoding='utf-8', newline='') as f:
    for r in csv.DictReader(f):
        if r['dataset'] != DAVIS:
            continue
        i, c, b = r['input_id'], r['codec'], int(r['bytes'])
        grp[i] = r['group']
        prim[c][i] = b
        if c == 'bdlc':
            s0[c][i] = b - lsb[i] / 8
        elif c in pi_cfg:
            s0[c][i] = b - sigma_star(int(r['K']))
            if c == pi_cfg[0]:
                sig_davis.append(sigma_star(int(r['K'])))
        else:
            s0[c][i] = b
        if c == 'ecc_direct' and r['timed'] == 'True':
            ecc_t['null_e'].append(float(r['null_encode_s'])); ecc_t['null_d'].append(float(r['null_decode_s']))
            ecc_t['net_e'].append(float(r['encode_s'])); ecc_t['net_d'].append(float(r['decode_s']))
        if c == 'bdlc' and r['timed'] == 'True':
            ecc_t.setdefault('bdlc_e', []).append(float(r['encode_s']))
            ecc_t.setdefault('bdlc_d', []).append(float(r['decode_s']))
ecc_cfg = [c for c in competitors if c in ECC]
rest_cfg = [c for c in competitors if c not in ECC]


def cluster_d(D, refs):
    num, den = defaultdict(float), defaultdict(float)
    for i in D['bdlc']:
        num[grp[i]] += D['bdlc'][i]
        den[grp[i]] += min(D[c][i] for c in refs)
    return [math.log(num[g] / den[g]) for g in sorted(num)]


for D, tag in ((prim, 'Prim'), (s0, 'Szero')):
    for refs, h, side in ((ecc_cfg, 'Bone', 3), (rest_cfg, 'Btwo', 2)):
        d = cluster_d(D, refs)
        n, w, p1, p2 = MR.sign_test(d)
        lo, hi = MR.boot_ci(d)
        est, clo, chi = MR.delta_pct(float(np.mean(d))), MR.delta_pct(hi), MR.delta_pct(lo)
        if tag == 'Prim':           # the recomputation must reproduce the run's own B1/B2 exactly
            ref = T[(DAVIS, 'B1' if h == 'Bone' else 'B2')]
            assert abs(est - float(ref['estimate'])) < 1e-9 and abs(clo - float(ref['ci95_low'])) < 1e-9, h
            continue
        macro(tag + h + 'Delta', fnum(est, 1), rel(P_PER))
        macro(tag + h + 'DeltaAbs', fnum(abs(est), 1), rel(P_PER))
        macro(tag + h + 'Lo', fnum(clo, 1), rel(P_PER))
        macro(tag + h + 'Hi', fnum(chi, 1), rel(P_PER))
        macro(tag + h + 'LoAbs', fnum(min(abs(clo), abs(chi)), 1), rel(P_PER))
        macro(tag + h + 'HiAbs', fnum(max(abs(clo), abs(chi)), 1), rel(P_PER))
        macro(tag + h + 'Better', str(w), rel(P_PER))
        macro(tag + h + 'Psign', fp(p2 if h == 'Bone' else p1), rel(P_PER))
        S0ROWS = globals().setdefault('S0ROWS', {})
        S0ROWS[h] = (est, clo, chi, w, len(d), p2 if h == 'Bone' else p1)
sig_davis.sort()
macro('SigmaMinDAVIS', str(sig_davis[0]), rel(P_PER))
macro('SigmaMedDAVIS', '%g' % statistics.median(sig_davis), rel(P_PER))
macro('SigmaMaxDAVIS', str(sig_davis[-1]), rel(P_PER))
lsb_d = sorted(lsb[i] / 8 for i in prim['bdlc'])
macro('LabelSetMedBytesDAVIS', fnum(statistics.median(lsb_d), 2), rel(P_BB))
macro('LabelSetMaxBytesDAVIS', fnum(lsb_d[-1], 2), rel(P_BB))
shares_sigma = [100 * sum(prim[c][i] - s0[c][i] for i in prim[c]) / sum(prim[c].values()) for c in pi_cfg]
macro('SigmaShareMin', fnum(min(shares_sigma), 1), rel(P_PER))
macro('SigmaShareMax', fnum(max(shares_sigma), 1), rel(P_PER))
macro('NpiConfigs', str(len(pi_cfg)), rel(P_PROTO))
# fixed per-call cost subtracted from the command-line timings (ECC-2026, direct mode, timed DAVIS maps)
for k, name in (('null_e', 'NullEncECCms'), ('null_d', 'NullDecECCms'), ('net_e', 'NetEncECCms'),
                ('net_d', 'NetDecECCms'), ('bdlc_e', 'NetEncBDLCms'), ('bdlc_d', 'NetDecBDLCms')):
    assert len(ecc_t[k]) == int(S[(DAVIS, 'bdlc')]['images_timed']), k
    macro(name, fnum(1000 * statistics.median(ecc_t[k]), 2), rel(P_PER))

# ---------------------------------------------------------------- protocol C: COCO-Stuff val2017 (PROTOKOL_C_UZ.md)
# Second hash-locked run with the same harness, configurations, settings and parameters as protocol B; only the
# inputs differ. Every map is its own cluster. Hypotheses C1-C4 are B1-B4 on these maps; the run's report names
# its rows B1-B3 because it is the same code (bench/make_reports.py).
COCO = 'COCO-Stuff_val2017'
RUN_C = os.path.join(BDLC, 'runs', '20261030_134701_test_C')
RES_C = os.path.join(RUN_C, 'results')
P_PROTO_C = os.path.join(BDLC, 'protocol_C.json')
P_SUMMARY_C = os.path.join(RES_C, 'tables', 'summary_by_dataset.csv')
P_PAIR_C = os.path.join(RES_C, 'tables', 'pairwise_vs_bdlc.csv')
P_PER_C = os.path.join(RES_C, 'tables', 'per_image.csv')
P_TESTS_C = os.path.join(RES_C, 'statistics', 'protocol_B_tests.csv')
P_PARETO_C = os.path.join(RES_C, 'statistics', 'pareto_B4.csv')
P_VB_C = os.path.join(RES_C, 'statistics', 'virtual_best.csv')
P_SPEED_C = os.path.join(RES_C, 'statistics', 'speed_coefficients.csv')
P_BB_C = os.path.join(RUN_C, 'byte_breakdown.csv')
P_STATUS_C = os.path.join(RUN_C, 'status.json')
P_REPST_C = os.path.join(RES_C, 'reports', 'status.json')
P_ERR_C = os.path.join(RES_C, 'reports', 'errors.md')
proto_c = json.load(open(P_PROTO_C, encoding='utf-8'))
status_c = json.load(open(P_STATUS_C, encoding='utf-8'))
repst_c = json.load(open(P_REPST_C, encoding='utf-8'))
fail_c = json.load(open(os.path.join(RUN_C, 'failures.json'), encoding='utf-8'))
na_c = json.load(open(os.path.join(RUN_C, 'not_applicable.json'), encoding='utf-8'))
assert status_c['status'] == 'COMPLETE' and status_c['failures'] == 0 and fail_c == [] and na_c == []
assert status_c['measured_pairs'] == status_c['expected_pairs'] == 41 * len(proto_c['inputs'])
assert status_c['timed_pairs'] == status_c['expected_timed_pairs'] == 41 * proto_c['parameters']['timing_images']
# protocol C must equal protocol B in everything but its inputs (and the script that built them)
for k in ('codecs', 'external_tools', 'packages', 'platform', 'python', 'cpu', 'codec_freeze', 'split', 'unavailable'):
    assert proto_c[k] == proto[k], k
assert {k: v for k, v in proto_c['parameters'].items() if k != 'timing_images'} == \
       {k: v for k, v in proto['parameters'].items() if k != 'timing_images'}
assert {k for k in set(proto['code_sha256']) | set(proto_c['code_sha256'])
        if proto['code_sha256'].get(k) != proto_c['code_sha256'].get(k)} == {'tools/build_manifest_C.py'}
# the report's self-check could not re-read virtual_best.csv (a field of 5,000 cluster values exceeds the default
# csv field limit); the file itself is complete and must reproduce the test rows
assert repst_c['artifacts_failed'] == 1 and 'virtual_best.csv: Error: field larger than field limit' in open(P_ERR_C, encoding='utf-8').read()
csv.field_size_limit(10 ** 9)
summary_c = read_csv(P_SUMMARY_C)
SC = {r['codec']: r for r in summary_c if r['scope'] == COCO}
pair_c = {r['reference']: r for r in read_csv(P_PAIR_C) if r['scope'] == COCO}
TC = {r['hypothesis'][:2]: r for r in read_csv(P_TESTS_C) if r['scope'] == COCO}
pareto_c = [r for r in read_csv(P_PARETO_C) if r['scope'] == COCO]
vb_c = {r['oracle']: r for r in read_csv(P_VB_C) if r['scope'] == COCO}
bb_c = read_csv(P_BB_C)
assert sorted(SC) == sorted(codecs) and len(pareto_c) == 35 and len(bb_c) == len(proto_c['inputs'])
assert abs(float(vb_c['ECC_only']['delta_pct']) - float(TC['B1']['estimate'])) < 1e-9
assert abs(float(vb_c['all_except_ECC']['delta_pct']) - float(TC['B2']['estimate'])) < 1e-9
for c in SC:
    NAME.setdefault(c, SC[c]['codec_name'])
with open(P_PROTO_C, 'rb') as f:
    macro('ProtocolHashC', hashlib.sha256(f.read()).hexdigest()[:8], 'SHA-256 of BDLC/protocol_C.json (first 8 hex digits)')
macro('NmapsCOCO', fint(len(proto_c['inputs'])), rel(P_PROTO_C))
macro('NtimedCOCO', fint(proto_c['parameters']['timing_images']), rel(P_PROTO_C))
macro('NprimaryPairsC', fint(repst_c['primary_pairs']), rel(P_REPST_C))
macro('NtimedPairsC', fint(repst_c['timed_pairs']), rel(P_REPST_C))
macro('NprimaryPairsAll', fint(repst['primary_pairs'] + repst_c['primary_pairs']), rel(P_REPST) + ' + ' + rel(P_REPST_C))
macro('NmapsAll', fint(len(proto['inputs']) + len(proto_c['inputs'])), rel(P_PROTO) + ' + ' + rel(P_PROTO_C))
macro('NfailuresC', str(len(fail_c)), rel(RUN_C) + '/failures.json')
ks_c = [int(r['K']) for r in bb_c]
px_c = [int(r['pixels']) for r in bb_c]
macro('KminCOCO', str(min(ks_c)), rel(P_BB_C))
macro('KmedCOCO', '%g' % statistics.median(ks_c), rel(P_BB_C))
macro('KmaxCOCO', str(max(ks_c)), rel(P_BB_C))
# class values that occur in the 5,000 maps (255 = unlabeled), counted from the converted input maps of the run
import tifffile
P_MAN_C = os.path.join(BDLC, 'manifest_C.csv')
vals_c = set()
for r in read_csv(P_MAN_C):
    vals_c.update(np.unique(tifffile.imread(os.path.join(BDLC, r['path']))).tolist())
assert max(vals_c) == 255 and max(v for v in vals_c if v != 255) <= 181
NCLASS_C = len(vals_c - {255})
macro('NclassesCOCO', str(NCLASS_C), rel(P_MAN_C) + ' (input maps)')
macro('BppCOCO', '%.5f' % float(SC['bdlc']['micro_bpp']), rel(P_SUMMARY_C))
macro('EncMPixCOCO', fnum(float(SC['bdlc']['encode_MPix_s']), 0), rel(P_SUMMARY_C))
macro('DecMPixCOCO', fnum(float(SC['bdlc']['decode_MPix_s']), 0), rel(P_SUMMARY_C))


def log10_binom_tail(w, n):
    """log10 P(X >= w) for X ~ Bin(n, 1/2), computed in log space (no underflow)."""
    lt = [math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1) - n * math.log(2) for k in range(w, n + 1)]
    m = max(lt)
    return (m + math.log(sum(math.exp(x - m) for x in lt))) / math.log(10)


def fp_c(p, check=None):
    """p-values of protocol C. The report writes 0.0 when a double underflows; such values are written as
    < 10^-300, and `check` = (w, n, two_sided) recomputes the exact value in log space to justify that."""
    p = float(p)
    if p == 0.0:
        w, n, two = check
        assert log10_binom_tail(w, n) + (math.log10(2) if two else 0) < -300, (w, n)
        return r'$<10^{-300}$'
    return fp(p)


# per-map log ratios (every map is a cluster), primary and S0, with the run's own statistics code
lsb_c = {r['input_id']: float(r['label_set_bits']) for r in bb_c}
prim_c, s0_c = defaultdict(dict), defaultdict(dict)
ctimes = defaultdict(dict)
with open(P_PER_C, encoding='utf-8', newline='') as f:
    for r in csv.DictReader(f):
        i, c, b = r['input_id'], r['codec'], int(r['bytes'])
        prim_c[c][i] = b
        s0_c[c][i] = b - lsb_c[i] / 8 if c == 'bdlc' else (b - sigma_star(int(r['K'])) if c in pi_cfg else b)
SZC = {}
for D, tag in ((prim_c, 'Prim'), (s0_c, 'Szero')):
    for refs, h in ((ecc_cfg, 'Cone'), (rest_cfg, 'Ctwo')):
        d = [math.log(D['bdlc'][i] / min(D[c][i] for c in refs)) for i in sorted(D['bdlc'])]
        n, w, p1, p2 = MR.sign_test(d)
        lo, hi = MR.boot_ci(d)
        est, clo, chi = MR.delta_pct(float(np.mean(d))), MR.delta_pct(hi), MR.delta_pct(lo)
        ties = sum(x == 0 for x in d)
        p = p2 if h == 'Cone' else p1
        chk = (n - w, n, True) if h == 'Cone' else (w, n, False)
        if tag == 'Prim':           # must reproduce the run's own C1/C2 exactly
            ref = TC['B1' if h == 'Cone' else 'B2']
            assert abs(est - float(ref['estimate'])) < 1e-9 and abs(clo - float(ref['ci95_low'])) < 1e-9, h
            assert str(w) == ref['groups_ours_better'], h
            macro(h + 'Ties', str(ties), rel(P_PER_C))
            continue
        macro('Szero' + h + 'Delta', fnum(est, 1), rel(P_PER_C))
        macro('Szero' + h + 'Lo', fnum(clo, 1), rel(P_PER_C))
        macro('Szero' + h + 'Hi', fnum(chi, 1), rel(P_PER_C))
        macro('Szero' + h + 'Better', fint(w), rel(P_PER_C))
        SZC[h] = (est, clo, chi, w, len(d), fp_c(p, chk))
c1, c2, c3 = TC['B1'], TC['B2'], TC['B3']
n1 = int(c1['groups'])
macro('ConeDelta', fnum(float(c1['estimate']), 1), rel(P_TESTS_C))
macro('ConeDeltaAbs', fnum(abs(float(c1['estimate'])), 1), rel(P_TESTS_C))
macro('ConeLoAbs', fnum(abs(float(c1['ci95_high'])), 1), rel(P_TESTS_C))
macro('ConeHiAbs', fnum(abs(float(c1['ci95_low'])), 1), rel(P_TESTS_C))
macro('ConeBetter', fint(c1['groups_ours_better']), rel(P_TESTS_C))
macro('ConeGroups', fint(n1), rel(P_TESTS_C))
macro('ConePsign', fp_c(c1['p_sign']), rel(P_TESTS_C))
macro('ConePholm', fp_c(c1['p_holm']), rel(P_TESTS_C))
macro('CtwoDelta', fnum(float(c2['estimate']), 1), rel(P_TESTS_C))
macro('CtwoLo', fnum(float(c2['ci95_low']), 1), rel(P_TESTS_C))
macro('CtwoHi', fnum(float(c2['ci95_high']), 1), rel(P_TESTS_C))
macro('CtwoBetter', fint(c2['groups_ours_better']), rel(P_TESTS_C))
enc_c, dec_c = [float(x) for x in c3['estimate'].split('/')]
macro('CthreeEnc', fnum(enc_c, 1), rel(P_TESTS_C))
macro('CthreeDec', fnum(dec_c, 1), rel(P_TESTS_C))
ge_c, gd_c = [x.strip().split()[0] for x in c3['groups_ours_better'].split('/')]
macro('CthreeEncGroups', fint(ge_c), rel(P_TESTS_C))
macro('CthreeDecGroups', fint(gd_c), rel(P_TESTS_C))
macro('CthreeGroups', fint(c3['groups']), rel(P_TESTS_C))
macro('CthreePholm', fp_c(c3['p_holm']), rel(P_TESTS_C))
macro('CfourDominating', str(sum(r['bdlc_pareto_dominated_by_ref'] == 'True' for r in pareto_c)), rel(P_PARETO_C))
macro('CfourMaxGroups', str(max(int(r['groups_ref_smaller_and_faster_both']) for r in pareto_c)), rel(P_PARETO_C))
# pooled comparisons on COCO-Stuff (ratio of sums, as Table tab:compare-coco)
for c, tag in (('ecc_direct', 'ECC'), ('ecc_pi', 'ECCpi'), ('crackle_mo0_zstd19', 'Crackle'), ('jpegls', 'JPEGLS'),
               ('zstd3', 'Zstdthree'), ('zstd19', 'Zstdnineteen'), ('flif_pi_e100', 'FLIF'), ('jpegxl10', 'JXLten'),
               ('hevc_scc_direct', 'HEVC')):
    macro('Gain' + tag + 'COCO', fnum(float(pair_c[c]['size_gain_pct']), 1), rel(P_PAIR_C))
    macro('GainAbs' + tag + 'COCO', fnum(abs(float(pair_c[c]['size_gain_pct'])), 1), rel(P_PAIR_C))
    macro('Enc' + tag + 'COCO', fmag(pair_c[c]['encode_speedup']), rel(P_PAIR_C))
    macro('Dec' + tag + 'COCO', fmag(pair_c[c]['decode_speedup']), rel(P_PAIR_C))
    macro('Bpp' + tag + 'COCO', '%.5f' % float(SC[c]['micro_bpp']), rel(P_SUMMARY_C))
    macro('EncMPix' + tag + 'COCO', fmag(SC[c]['encode_MPix_s']), rel(P_SUMMARY_C))
    macro('DecMPix' + tag + 'COCO', fmag(SC[c]['decode_MPix_s']), rel(P_SUMMARY_C))
    macro('SizeWin' + tag + 'COCO', fint(pair_c[c]['size_wins']), rel(P_PAIR_C))
best_c = min((c for c in competitors if c not in ECC), key=lambda c: float(SC[c]['micro_bpp']))
macro('BestNonECCNameCOCO', tex(NAME[best_c]), rel(P_SUMMARY_C))
macro('GainBestNonECCCOCO', fnum(float(pair_c[best_c]['size_gain_pct']), 1), rel(P_PAIR_C))
for c, tag in (('jpegls', 'JPEGLS'), ('zstd3', 'Zstdthree'), ('zstd19', 'Zstdnineteen')):
    macro('Ratio' + tag + 'COCO', fnum(float(SC[c]['micro_bpp']) / float(SC['bdlc']['micro_bpp']), 1), rel(P_SUMMARY_C))
won_enc_c = [c for c in competitors if float(pair_c[c]['encode_speedup']) > 1]
won_dec_c = [c for c in competitors if float(pair_c[c]['decode_speedup']) > 1]
won_size_c = [c for c in competitors if float(pair_c[c]['size_gain_pct']) > 0]
macro('NwonEncCOCO', str(len(won_enc_c)), rel(P_PAIR_C))
macro('NwonDecCOCO', str(len(won_dec_c)), rel(P_PAIR_C))
macro('NwonAllCOCO', str(len([c for c in won_size_c if c in won_enc_c and c in won_dec_c])), rel(P_PAIR_C))
macro('LostEncNamesCOCO', andjoin(tex(NAME[c]) for c in competitors if c not in won_enc_c), rel(P_PAIR_C))
macro('LostDecNamesCOCO', andjoin(tex(NAME[c]) for c in competitors if c not in won_dec_c), rel(P_PAIR_C))
macro('LostSizeNamesCOCO', andjoin(tex(NAME[c]) for c in competitors if c not in won_size_c), rel(P_PAIR_C))
for c, tag in (('bdlc_nok2', 'NoKtwo'), ('bdlc_noslope', 'NoSlope'), ('bdlc_nopass', 'NoPass'),
               ('bdlc_uniform', 'Uniform'), ('bdlc_crc', 'CRC')):
    v = fnum(100 * (float(SC[c]['total_bytes']) / float(SC['bdlc']['total_bytes']) - 1), 1)
    macro('Abl' + tag + 'COCO', '0.0' if v == '\\textminus 0.0' else v, rel(P_SUMMARY_C))
# label-set cost on COCO-Stuff (S0 context)
sig_c = sorted(sigma_star(k) for k in ks_c)
macro('SigmaMinCOCO', str(sig_c[0]), rel(P_BB_C))
macro('SigmaMaxCOCO', str(sig_c[-1]), rel(P_BB_C))
macro('LabelSetMedBytesCOCO', fnum(statistics.median(v / 8 for v in lsb_c.values()), 1), rel(P_BB_C))
# from here on, the COCO-Stuff rows are addressed like the scopes of protocol B
S.update({(COCO, c): r for c, r in SC.items()})
pair.update({(COCO, c): r for c, r in pair_c.items()})
SCOPE_NAME[COCO] = 'COCO-Stuff val2017'
# information shares of BDLC on COCO-Stuff (same decomposition as for protocol B; Fig. fig:bits)
_tot = sum(float(r['model_bits_total']) for r in bb_c)
_parts = [sum(float(r[k]) for r in bb_c for k in ks) for _, ks in COMP]
assert abs(sum(_parts) - _tot) <= 1e-6 * _tot + 1
shares[COCO] = [100 * p / _tot for p in _parts]
assert all(100 - v[0] > 50 for v in shares.values())                  # boundary geometry (all but labels) carries most
assert shares[COCO][0] > max(v[0] for k, v in shares.items() if k != COCO)   # labels: largest share on COCO-Stuff
assert all(v[2] > 50 for k, v in shares.items() if k != COCO)               # protocol B: mostly displacements
# "descriptively also for the cell maps": no competitor dominates BDLC, or beats it in all three, in any CTC sequence
assert all(r['bdlc_pareto_dominated_by_ref'] == 'False' and r['groups_ref_smaller_and_faster_both'] == '0'
           for r in pareto if r['scope'] in CTC)
macro('ShareGeomCOCO', fnum(100 - shares[COCO][0], 0), rel(P_BB_C))
macro('ShareDispCOCO', fnum(shares[COCO][2], 0), rel(P_BB_C))
macro('ShareLabelCOCO', fnum(shares[COCO][0], 0), rel(P_BB_C))
# the words of Section 6.8 (sec:coco) that are not numbers, checked against the data
assert float(c1['estimate']) < 0 and float(c1['ci95_low']) < float(c1['ci95_high']) < 0     # ECC-2026 smaller, CI excludes 0
assert float(c1['estimate']) > float(T[(DAVIS, 'B1')]['estimate'])                          # smaller gap than on DAVIS
assert float(c2['estimate']) > 0 and float(c2['ci95_low']) > 0                              # BDLC smaller than the rest
assert ge_c == gd_c == c3['groups']                                                          # faster on all timed maps
assert sum(r['bdlc_pareto_dominated_by_ref'] == 'True' for r in pareto_c) == 0
assert max(int(r['groups_ref_smaller_and_faster_both']) for r in pareto_c) == 0           # not even one timed map
assert [c for c in competitors if c not in won_enc_c and c in won_dec_c] == []              # enc-faster codecs are dec-faster too
lost_c = [c for c in competitors if c not in won_dec_c]
r_c = {c: float(SC[c]['micro_bpp']) / float(SC['bdlc']['micro_bpp']) for c in lost_c}
assert sorted(lost_c) == sorted(['zstd3', 'zstd19', 'jpegls'])
assert min(r_c, key=r_c.get) == 'zstd19' and max(r_c, key=r_c.get) == 'jpegls'             # the stated ratio range
abl = {c: float(SC[c]['total_bytes']) / float(SC['bdlc']['total_bytes']) - 1 for c in VARIANTS}
assert abl['bdlc_nok2'] > abl['bdlc_noslope'] > max(abl['bdlc_nopass'], abl['bdlc_uniform'], abl['bdlc_crc'])
assert abs(abl['bdlc_nopass']) < 0.0005 and abl['bdlc_uniform'] < 0                         # PASS: same to 0.1 %; uniform smaller
assert abs(float(T[(DAVIS, 'B1')]['estimate']) - S0ROWS['Bone'][0]) < abs(float(c1['estimate']) - SZC['Cone'][0])  # label set weighs more
assert abs(float(T[(DAVIS, 'B2')]['estimate']) - S0ROWS['Btwo'][0]) < abs(float(c2['estimate']) - SZC['Ctwo'][0])
assert statistics.median(ks_c) > statistics.median(int(r['K']) for r in bb if r['dataset'] == DAVIS)

# ---------------------------------------------------------------- tables
def write(name, text, sources):
    p = os.path.join(TAB, name)
    with open(p, 'w', encoding='utf-8', newline='\n') as f:
        f.write('%% generated by paper_CEE/tools/make_paper_assets.py from: %s\n' % ', '.join(sources))
        f.write(text)
    MANIFEST.append((rel(p), sources))


# The CAS class takes a table's position only as a key, [pos=...]; a bare [!htbp] is silently ignored and
# the table goes to the top of a page only (cas-common.sty, keys cas/tbl).
# Table: datasets
lines = []
for ds in [DAVIS] + CTC:
    rows = [r for r in bb if r['dataset'] == ds]
    px = [int(r['pixels']) for r in rows]
    ks = [int(r['K']) for r in rows]
    name = {DAVIS: 'DAVIS 2017 (primary)', 'Fluo-N2DH-SIM+_GT_SEG': 'Fluo-N2DH-SIM+$^{a}$'}.get(ds, SCOPE_NAME[ds])
    lines.append('%s & %d & %s & %s & %s & %d/%g/%d \\\\' % (
        name, len(seqs[ds]), fint(len(rows)), fint(S[(ds, 'bdlc')]['images_timed']),
        ('%s' % fint(px[0])) if min(px) == max(px) else '%s--%s' % (fint(min(px)), fint(max(px))),
        min(ks), statistics.median(ks), max(ks)))
lines.append(r'\midrule')
lines.append(r'COCO-Stuff val2017$^{b}$ & %s & %s & %s & %s--%s & %d/%g/%d \\' % (
    fint(len(bb_c)), fint(len(bb_c)), fint(SC['bdlc']['images_timed']), fint(min(px_c)), fint(max(px_c)),
    min(ks_c), statistics.median(ks_c), max(ks_c)))
write('tab_datasets.tex', r'''\begin{table}[pos=!htbp]
\caption{Test data. Clusters are the units of the statistical analysis: video sequences in protocol B, single maps in protocol C. Timed maps are the maps of the timing phase; $K$ is the number of distinct labels in a map. The CTC data sets are reported descriptively.}\label{tab:datasets}
\small
\begin{tabular*}{\tblwidth}{@{\extracolsep{\fill}}lrrrrr@{}}
\toprule
Data set & Clusters & Maps & Timed maps & Pixels per map & $K$ (min/med./max) \\
\midrule
\multicolumn{6}{@{}l}{\textit{Protocol B}} \\
''' + '\n'.join(lines[:-2]) + '\n' + r'\midrule' + '\n' + r'\multicolumn{6}{@{}l}{\textit{Protocol C}} \\' + '\n' + lines[-1] + r'''
\bottomrule
\end{tabular*}
\par\smallskip{\footnotesize $^{a}$\,Simulated maps; never pooled with the real data. $^{b}$\,Semantic maps; %d stuff and thing classes and an ``unlabeled'' value occur in them. Every map is its own cluster.}
\end{table}
''' % NCLASS_C, [rel(P_BB), rel(P_SUMMARY), rel(P_BB_C), rel(P_SUMMARY_C)])

# Table: codec configurations
def sigma_of(c):
    return r'$\sigma^{*}(K)$' if 'sigma*(K)' in proto['codecs'][c][2] else '0'


def eta_of(c):
    return r'$\eta$' if proto['codecs'][c][1].startswith('varint_hw') else '0'


def joined(vals):
    v = sorted(set(vals), key=lambda s: (s != '0', s))
    return ' / '.join(v)


# compact overview in the main text (groups of configurations; sigma and eta come from the protocol file)
COMPACT = [
    ('BDLC and its five variants', ['bdlc'] + VARIANTS, r'this work; Numba \VerNumba'),
    ('ECC-2026: direct, rank map', ['ecc_direct', 'ecc_pi'], r'commit fe3f2f1 with the fix of Sec.~\ref{sec:codecs}; command line'),
    (r'Crackle: Markov order 0, 3; each also $+$ zstd', ['crackle_mo0', 'crackle_mo3', 'crackle_mo0_zstd19', 'crackle_mo3_zstd19'], r'crackle-codec \VerCrackle'),
    (r'compressed\_segmentation $+$ gzip', ['cseg_gzip9'], r'compressed-segmentation \VerCseg'),
    ('Compresso', ['compresso'], 'commit b1f7fd6, C++ wrapper; command line'),
    ('HEVC SCC: direct, rank map', ['hevc_scc_direct', 'hevc_scc_pi'], 'HM-16.21+SCM-8.8; command line'),
    ('JBIG1: Gray and binary bit planes', ['jbig_gray_pi', 'jbig_binary_pi'], 'JBIG-KIT 2.1; command line'),
    ('FLIF: 16-bit, rank map; effort 60, 100', ['flif_u16_e60', 'flif_u16_e100', 'flif_pi_e60', 'flif_pi_e100'], 'FLIF 0.4; command line'),
    ('JPEG XL: effort 7, 9, 10', ['jpegxl7', 'jpegxl9', 'jpegxl10'], r'imagecodecs \VerImagecodecs'),
    ('JPEG-LS, JPEG 2000, HTJ2K, PNG', ['jpegls', 'jpeg2k', 'htj2k', 'png16'], 'imagecodecs (CharLS, OpenJPEG, OpenJPH)'),
    (r'LERC, LERC $+$ zstd', ['lerc', 'lerc_zstd'], 'imagecodecs'),
    ('zlib, xz, bzip2, Zstandard (3, 19), Brotli, Blosc2', ['zlib9', 'lzma9e', 'bz2_9', 'zstd3', 'zstd19', 'brotli11', 'blosc2_zstd_bitshuffle'],
     r'Python standard library; python-zstandard \VerZstandard; imagecodecs'),
    (r'Palette indices $+$ zstd, $+$ xz', ['palette_zstd19', 'palette_lzma9e'], r'Python standard library; python-zstandard'),
    ('RVC (earlier codec)', ['rvc'], 'this project'),
]
assert sorted(c for _, cs, _ in COMPACT for c in cs) == sorted(codecs), 'compact table must cover all 41 configurations'
rows = ['%s & %d & %s & %s & %s \\\\' % (g, len(cs), impl, joined(sigma_of(c) for c in cs), joined(eta_of(c) for c in cs))
        for g, cs, impl in COMPACT]
write('tab_codecs.tex', r'''\begin{table}[pos=!htbp]
\caption{The %d configurations of protocols B and C, grouped by codec. $\sigma$ and $\eta$ are the bytes added to a stream for the label set and for the image size (Eq.~\eqref{eq:bytes}); ``0 / $\sigma^{*}(K)$'' means 0 for the direct and $\sigma^{*}(K)$ for the rank-map configurations. The settings of every configuration are listed in Appendix~\ref{app:settings}.}\label{tab:codecs}
\footnotesize
\begin{tabular*}{\tblwidth}{@{}p{0.36\textwidth}cp{0.36\textwidth}cc@{}}
\toprule
Codec and configurations & Number & Implementation & $\sigma$ & $\eta$ \\
\midrule
''' % len(codecs) + '\n'.join(rows) + r'''
\midrule
Total & %d & & & \\
\bottomrule
\end{tabular*}
\end{table}
''' % len(codecs), [rel(P_PROTO)])

# full settings, appendix: abridged wording of the protocol descriptions (no repository paths, no internal flags)
SHORT = {
    'bdlc': 'model 1 (initial table T1), no CRC',
    'bdlc_crc': 'model 1, CRC-32 of the pixels in the header',
    'bdlc_uniform': 'model 2 (uniform initial probabilities)',
    'bdlc_noslope': 'model 1, slope contexts and prediction off',
    'bdlc_nok2': 'model 1, second label candidate off',
    'bdlc_nopass': 'model 1, PASS mode off',
    'ecc_direct': r'label values $\le 255$ as 8-bit 4:0:0 YUV, one frame (ECC-2026 stores its palette)',
    'ecc_pi': r'rank map $\pi(x)$ as 8-bit 4:0:0 YUV, one frame; commit fe3f2f1 with the fix of Sec.~\ref{sec:codecs}',
    'crackle_mo0': 'Markov model order 0, one thread',
    'crackle_mo3': 'Markov model order 3, one thread',
    'crackle_mo0_zstd19': 'order-0 stream $+$ zstd level 19',
    'crackle_mo3_zstd19': 'order-3 stream $+$ zstd level 19',
    'cseg_gzip9': r'32-bit labels, volume $H\times W\times1$, blocks $8\times8\times1$, gzip level 9',
    'compresso': r'commit b1f7fd6, C++ wrapper with the Python-package defaults ($4\times4\times1$ steps, connectivity 4)',
    'png16': '16-bit grey, zlib level 9',
    'jpegls': 'CharLS, lossless (NEAR $=0$)',
    'jpegxl7': 'lossless, effort 7, one thread, bare code stream',
    'jpegxl9': 'lossless, effort 9, one thread, bare code stream',
    'jpegxl10': 'lossless, effort 10, one thread, bare code stream',
    'jpeg2k': 'OpenJPEG, reversible 5/3 wavelet, J2K code stream, one thread',
    'htj2k': 'OpenJPH, reversible, code stream',
    'lerc': 'maximum error 0',
    'lerc_zstd': 'maximum error 0, $+$ zstd level 19',
    'hevc_scc_pi': r'HM-16.21+SCM-8.8, intra main SCC, lossless, palette on; rank map $\pi(x)$ as 8-bit 4:0:0',
    'hevc_scc_direct': r'as HEVC SCC (rank map), label values $\le 255$',
    'jbig_gray_pi': r'JBIG-KIT 2.1, sequential; bit planes of $\pi(x)$, Gray code',
    'jbig_binary_pi': r'JBIG-KIT 2.1, sequential; bit planes of $\pi(x)$, binary code',
    'flif_u16_e60': 'FLIF 0.4, 16-bit PGM, effort 60 (default)',
    'flif_u16_e100': 'FLIF 0.4, 16-bit PGM, effort 100',
    'flif_pi_e60': r'FLIF 0.4, 8-bit PGM of $\pi(x)$, effort 60',
    'flif_pi_e100': r'FLIF 0.4, 8-bit PGM of $\pi(x)$, effort 100',
    'zlib9': 'level 9',
    'lzma9e': 'preset 9 with the extreme flag',
    'zstd3': 'level 3, one thread',
    'zstd19': 'level 19, one thread',
    'brotli11': 'quality 11',
    'bz2_9': 'level 9',
    'blosc2_zstd_bitshuffle': 'zstd level 9, bit shuffle, element size 2 bytes, one thread',
    'palette_zstd19': 'palette indices $+$ zstd level 19',
    'palette_lzma9e': 'palette indices $+$ xz preset 9 with the extreme flag',
    'rvc': 'earlier RVC codec, tiles of 64, spatial mode on',
}
assert sorted(SHORT) == sorted(codecs), 'settings table must cover all 41 configurations'
# every abridged entry must keep the protocol's key parameters (levels, efforts, orders) unchanged
for c, s in SHORT.items():
    for num in re.findall(r'(?<![\w.])(\d+)(?![\w.])', proto['codecs'][c][2].replace('fe3f2f1', '').replace('b1f7fd6', '')):
        if num in ('1', '0', '4', '2', '8', '16', '255', '65535', '64', '2000', '2026') or num in s:
            continue
        raise AssertionError('%s: number %s of the protocol description missing in the settings table' % (c, num))


def settings_rows(groups):
    out = []
    for fam in groups:
        out.append(r'\multicolumn{4}{@{}l}{\textit{%s}} \\' % fam)
        for c in codecs:
            if category(c) == fam or (fam == 'BDLC and variants' and category(c) in ('BDLC', 'BDLC variant')):
                name = tex(NAME[c])
                if len(NAME[c]) > 24 and ' + ' in NAME[c]:
                    # long names break before the last '+', the continuation indented like the name itself
                    head, tail = name.rsplit(' + ', 1)
                    name = head + r'\newline\hspace*{1em}+ ' + tail
                out.append(r'\quad %s & %s & %s & %s \\' % (name, SHORT[c], sigma_of(c), eta_of(c)))
    return out


for part, (groups, lab) in enumerate(((['BDLC and variants', 'ECC-2026', 'Segmentation codecs'], 'tab:settings-a'),
                                      (['Image and video codecs', 'General-purpose compressors', 'Earlier codec (RVC)'], 'tab:settings-b'))):
    write('tab_settings_%s.tex' % 'ab'[part], r'''\begin{table}[pos=!htbp]
\caption{Settings of the configurations, part %d of 2 (abridged from the protocol file). $\sigma$ and $\eta$ as in Table~\ref{tab:codecs}.}\label{%s}
\footnotesize
\begin{tabular*}{\tblwidth}{@{}p{0.26\textwidth}p{0.58\textwidth}cc@{}}
\toprule
Configuration & Settings & $\sigma$ & $\eta$ \\
\midrule
%s
\bottomrule
\end{tabular*}
\end{table}
''' % (part + 1, lab, '\n'.join(settings_rows(groups))), [rel(P_PROTO)])

# Table: pre-registered tests
def test_rows(scope):
    b1, b2, b3 = T[(scope, 'B1')], T[(scope, 'B2')], T[(scope, 'B3')]
    enc, dec = b3['estimate'].split('/')
    ge, gd = [x.strip().split()[0] for x in b3['groups_ours_better'].split('/')]
    n = b1['groups']
    nd = len([r for r in pareto if r['scope'] == scope and r['bdlc_pareto_dominated_by_ref'] == 'True'])
    def est(e, lo, hi):
        return r'%s [%s, %s]' % (fnum(e, 1), fnum(lo, 1), fnum(hi, 1))
    out = [
        r'B1 & Size vs.\ ECC-2026, two-sided & %s & %s/%s & %s & %s \\' % (
            est(float(b1['estimate']), float(b1['ci95_low']), float(b1['ci95_high'])),
            b1['groups_ours_better'], n, fp(b1['p_sign']), fp(b1['p_holm'])),
        r'B2 & Size vs.\ best of 33 others, one-sided & %s & %s/%s & %s & %s \\' % (
            est(float(b2['estimate']), float(b2['ci95_low']), float(b2['ci95_high'])),
            b2['groups_ours_better'], n, fp(b2['p_sign']), fp(b2['p_holm'])),
        r'B3 & Faster than ECC-2026, one-sided & enc.\ %s$\times$, dec.\ %s$\times$ & %s/%s, %s/%s & %s & %s \\' % (
            fnum(float(enc), 1), fnum(float(dec), 1), ge, n, gd, n, fp(b3['p_sign']), fp(b3['p_holm'])),
        r'B4 & Dominated by a competitor (descriptive) & %d of 35 competitors & -- & -- & -- \\' % nd,
        r'\midrule',
        r'\multicolumn{6}{@{}l}{\textit{Sensitivity analysis S0: no label-set cost for any configuration}} \\',
    ]
    for h, q, side in (('Bone', r'Size vs.\ ECC-2026', 'two-sided'), ('Btwo', r'Size vs.\ best of 33 others', 'one-sided')):
        e, lo, hi, w, nn, p = S0ROWS[h]
        out.append(r'B%s (S0) & %s, %s & %s & %d/%d & %s & -- \\' % ('1' if h == 'Bone' else '2', q, side, est(e, lo, hi), w, nn, fp(p)))
    return out


def test_rows_c():
    def est(e, lo, hi):
        return r'%s [%s, %s]' % (fnum(e, 1), fnum(lo, 1), fnum(hi, 1))
    n = fint(c1['groups'])
    nt = fint(c3['groups'])
    out = [
        r'\midrule',
        r'\multicolumn{6}{@{}l}{\textit{Protocol C: COCO-Stuff val2017, %s maps (each its own cluster)}} \\' % n,
        r'C1 & Size vs.\ ECC-2026, two-sided & %s & %s/%s & %s & %s \\' % (
            est(float(c1['estimate']), float(c1['ci95_low']), float(c1['ci95_high'])), fint(c1['groups_ours_better']), n,
            fp_c(c1['p_sign']), fp_c(c1['p_holm'])),
        r'C2 & Size vs.\ best of 33 others, one-sided & %s & %s/%s & %s & %s \\' % (
            est(float(c2['estimate']), float(c2['ci95_low']), float(c2['ci95_high'])), fint(c2['groups_ours_better']), n,
            SZC_P2, SZC_P2H),
        r'C3 & Faster than ECC-2026, one-sided & enc.\ %s$\times$, dec.\ %s$\times$ & %s/%s, %s/%s & %s & %s \\' % (
            fnum(enc_c, 1), fnum(dec_c, 1), fint(ge_c), nt, fint(gd_c), nt, fp_c(c3['p_sign']), fp_c(c3['p_holm'])),
        r'C4 & Dominated by a competitor (descriptive) & %d of 35 competitors & -- & -- & -- \\' % sum(
            r['bdlc_pareto_dominated_by_ref'] == 'True' for r in pareto_c),
    ]
    out.append(r'\midrule')
    out.append(r'\multicolumn{6}{@{}l}{\textit{Sensitivity analysis S0 on protocol C: no label-set cost for any configuration}} \\')
    for h, q, side in (('Cone', r'Size vs.\ ECC-2026', 'two-sided'), ('Ctwo', r'Size vs.\ best of 33 others', 'one-sided')):
        e, lo, hi, w, nn, p = SZC[h]
        out.append(r'C%s (S0) & %s, %s & %s & %s/%s & %s & -- \\' % ('1' if h == 'Cone' else '2', q, side, est(e, lo, hi),
                                                                    fint(w), fint(nn), p))
    return out


# C2 p-values: the run's report wrote 0.0 (double underflow); recompute the exact tail in log space
_d2 = [math.log(prim_c['bdlc'][i] / min(prim_c[c][i] for c in rest_cfg)) for i in sorted(prim_c['bdlc'])]
_n2, _w2, _, _ = MR.sign_test(_d2)
SZC_P2 = fp_c(c2['p_sign'], (_w2, _n2, False))
SZC_P2H = fp_c(c2['p_holm'], (_w2, _n2, False))   # Holm multiplies by 3: still far below 1e-300
assert log10_binom_tail(_w2, _n2) + math.log10(3) < -300
macro('CtwoPsign', SZC_P2, rel(P_PER_C))
write('tab_tests.tex', r'''\begin{table}[pos=!htbp]
\caption{Hypotheses of protocols B and C, each fixed before its run. Estimate for B1/C1 and B2/C2: $\Delta$ of Eq.~\eqref{eq:delta} in percent with its 95\%% cluster-bootstrap interval (positive means BDLC is smaller); for B3/C3: geometric-mean speed-up over the clusters. ``Better'' counts the clusters in which BDLC is better. $p$: sign test (B3/C3: the larger of the encoding and decoding $p$-values), Holm-adjusted within each protocol; ``$<10^{-300}$'' marks values that underflowed in double precision; they were bounded by an exact computation in log space. S0 is the sensitivity analysis of Section~\ref{sec:stats}.}\label{tab:tests}
\small
\begin{tabular*}{\tblwidth}{@{}lp{0.29\textwidth}p{0.20\textwidth}p{0.13\textwidth}ll@{}}
\toprule
Test & Hypothesis & Estimate & Better & $p$ & $p$ (Holm) \\
\midrule
\multicolumn{6}{@{}l}{\textit{Protocol B: DAVIS 2017, %s sequences}} \\
''' % T[(DAVIS, 'B1')]['groups'] + '\n'.join(test_rows(DAVIS) + test_rows_c()) + r'''
\bottomrule
\end{tabular*}
\end{table}
''', [rel(P_TESTS), rel(P_PARETO), rel(P_PER), rel(P_TESTS_C), rel(P_PARETO_C), rel(P_PER_C)])

# Table: BDLC vs every competitor (one scope)
def comparison_table(scope, label, caption_extra, star=True):
    order = sorted(competitors, key=lambda c: float(S[(scope, c)]['micro_bpp']))
    rows = []
    b = S[(scope, 'bdlc')]
    rows.append(r'\textbf{BDLC} & \textbf{%s} & -- & -- & -- & -- \\' % ('%.5f' % float(b['micro_bpp'])))
    for c in order:
        r = pair[(scope, c)]
        rows.append('%s & %s & %s & %s/%s/%s & %s & %s \\\\' % (
            tex(NAME[c]), '%.5f' % float(S[(scope, c)]['micro_bpp']),
            fnum(float(r['size_gain_pct']), 1), fint(r['size_wins']), fint(r['size_ties']), fint(r['size_losses']),
            fmag(r['encode_speedup']), fmag(r['decode_speedup'])))
    env = 'table*' if star else 'table'
    n_img = b['images_sized']
    n_t = b['images_timed']
    return r'''\begin{%s}[pos=%s]
\caption{%s: BDLC against each competitor configuration on the same %s maps (sizes) and %s timed maps (speed). Size gain $=100(1-\sum B_{\mathrm{BDLC}}/\sum B_{\mathrm{ref}})$; negative means BDLC is larger. Maps: BDLC smaller / equal / larger. Speed-up: ratio of summed net times; below 1 means BDLC is slower.%s}\label{%s}
\footnotesize
\begin{tabular*}{\tblwidth}{@{}LRRRRR@{}}
\toprule
Configuration & Size (bpp) & Size gain (\%%) & Maps & Encode speed-up & Decode speed-up \\
\midrule
%s
\bottomrule
\end{tabular*}
\end{%s}
''' % (env, '!htbp', SCOPE_NAME[scope], fint(n_img), fint(n_t), caption_extra, label,
       '\n'.join(rows), env)


write('tab_compare_davis.tex', comparison_table(DAVIS, 'tab:compare', ''), [rel(P_PAIR), rel(P_SUMMARY)])
# (the pooled table of all real maps of protocol B is not printed: 6,208 of its 6,262 maps are DAVIS maps, so it
# repeats Table tab:compare; its test results are reported in Section 6.1 and all its rows are in the run's CSV files)
for scope, lab in (('Fluo-N2DH-GOWT1_GT_SEG', 'tab:compare-gowt1'),
                   ('PhC-C2DL-PSC_GT_SEG', 'tab:compare-psc'), ('Fluo-N2DH-SIM+_GT_SEG', 'tab:compare-sim')):
    extra = ' Descriptive only (two sequences).'
    write('tab_compare_%s.tex' % lab.split('-')[1], comparison_table(scope, lab, extra), [rel(P_PAIR), rel(P_SUMMARY)])
write('tab_compare_coco.tex', comparison_table(COCO, 'tab:compare-coco', ' Protocol C.'), [rel(P_PAIR_C), rel(P_SUMMARY_C)])

# Table: ablation
rows = []
for c, what in (('bdlc_nok2', r'no second label candidate $k_2$'),
                ('bdlc_noslope', 'no slope contexts or prediction'),
                ('bdlc_nopass', 'no PASS mode'),
                ('bdlc_uniform', 'uniform start instead of T1'),
                ('bdlc_crc', 'with CRC-32 of the pixels')):
    cells = []
    for scope in (DAVIS, 'Fluo-N2DH-GOWT1_GT_SEG', 'PhC-C2DL-PSC_GT_SEG', COCO):
        a, b = float(S[(scope, c)]['total_bytes']), float(S[(scope, 'bdlc')]['total_bytes'])
        v = fnum(100 * (a / b - 1), 1)
        cells.append('0.0' if v in ('0.0', '\\textminus 0.0') else (v if v.startswith('\\textminus') else '+' + v))
    sp = speed[(DAVIS, c)]
    rows.append('%s & %s & %s & %s & %s & %s & %s \\\\' % (what, cells[0], cells[1], cells[2], cells[3],
                                                           fnum(1 / float(sp['encode_speedup']), 2),
                                                           fnum(1 / float(sp['decode_speedup']), 2)))
write('tab_ablation.tex', r'''\begin{table}[pos=!htbp]
\caption{BDLC variants. Size: bytes of the variant relative to BDLC, $100(\sum B_{\mathrm{var}}/\sum B_{\mathrm{BDLC}}-1)$, in percent; COCO: COCO-Stuff val2017 (protocol C). Speed: throughput of the variant relative to BDLC on the %s timed DAVIS maps (below 1 means slower).}\label{tab:ablation}
\small
\begin{tabular*}{\tblwidth}{@{\extracolsep{\fill}}lrrrrrr@{}}
\toprule
Variant & \multicolumn{4}{c}{Size change (\%%)} & \multicolumn{2}{c}{Relative speed} \\
\cmidrule(lr){2-5}\cmidrule(l){6-7}
 & DAVIS & GOWT1 & PSC & COCO & Encode & Decode \\
\midrule
''' % fint(S[(DAVIS, 'bdlc')]['images_timed']) + '\n'.join(rows) + r'''
\bottomrule
\end{tabular*}
\end{table}
''', [rel(P_SUMMARY), rel(P_SPEED), rel(P_SUMMARY_C)])

# Table: throughput and cold start
rows = []
for scope in [DAVIS] + CTC + [COCO]:
    r = S[(scope, 'bdlc')]
    rows.append('%s & %s & %s & %s \\\\' % (SCOPE_NAME[scope], fint(r['images_timed']),
                                           fnum(float(r['encode_MPix_s']), 0), fnum(float(r['decode_MPix_s']), 0)))
c1, c2 = cs[('bdlc', 'cache')], cs[('bdlc', 'nocache')]
write('tab_throughput.tex', r'''\begin{table}[pos=!htbp]
\caption{Throughput of BDLC (one pinned core, median of %s repeats, total pixels over total time) and cold-start cost (median of %s fresh processes).}\label{tab:throughput}
\begin{tabular*}{\tblwidth}{@{}LRRR@{}}
\toprule
Data set & Timed maps & Encode (MPix/s) & Decode (MPix/s) \\
\midrule
''' % (proto['parameters']['repeats'], proto['parameters']['coldstart_runs']) + '\n'.join(rows) + r'''
\midrule
Cold start & Import (ms) & First encode (ms) & First decode (ms) \\
\midrule
JIT cache present & %s & %s & %s \\
JIT cache empty & %s & %s & %s \\
\bottomrule
\end{tabular*}
\end{table}
''' % (fnum(float(c1['import_ms']), 0), fnum(float(c1['first_encode_ms']), 0), fnum(float(c1['first_decode_ms']), 0),
       fnum(float(c2['import_ms']), 0), fnum(float(c2['first_encode_ms']), 0), fnum(float(c2['first_decode_ms']), 0)),
      [rel(P_SUMMARY), rel(P_COLD)])

# Table: CTC (descriptive)
rows = []
for scope in CTC:
    b1, b2, b3 = T[(scope, 'B1')], T[(scope, 'B2')], T[(scope, 'B3')]
    enc, dec = b3['estimate'].split('/')
    rows.append(r'%s & %s & %s & %s & %s$\times$ / %s$\times$ \\' % (
        SCOPE_NAME[scope], b1['images'], fnum(float(b1['estimate']), 1), fnum(float(b2['estimate']), 1),
        fnum(float(enc), 1), fnum(float(dec), 1)))
write('tab_ctc.tex', r'''\begin{table}[pos=!htbp]
\caption{Cell Tracking Challenge maps (two sequences per data set; descriptive only). $\Delta$ as in Table~\ref{tab:tests}: B1 against ECC-2026, B2 against the best of the other 33 competitors; positive means BDLC is smaller. Speed-up against ECC-2026, geometric mean over the two sequences.}\label{tab:ctc}
\begin{tabular*}{\tblwidth}{@{}LRRRR@{}}
\toprule
Data set & Maps & $\Delta$ vs.\ ECC (\%) & $\Delta$ vs.\ best other (\%) & Speed-up vs.\ ECC (enc / dec) \\
\midrule
''' + '\n'.join(rows) + r'''
\bottomrule
\end{tabular*}
\end{table}
''', [rel(P_TESTS)])

# ---------------------------------------------------------------- I/O calibration of the command-line timing (B1)
# Post-hoc run with its own hash-locked protocol (posthoc/io_calibration/prepare.py): same worker, core and
# repeats as protocol B; ECC-2026 real vs. a pass-through program, plus BDLC, in one session.
IO_RUN = os.path.join(BDLC, 'runs', '20261030_175722_io_calibration')
P_IO = os.path.join(IO_RUN, 'summary.json')
P_IOPROT = os.path.join(IO_RUN, 'protocol_IO.json')
io = json.load(open(P_IO, encoding='utf-8'))
assert io['maps'] == int(S[(DAVIS, 'bdlc')]['images_timed']) and io['sequences'] == len(seqs[DAVIS])
with open(P_IOPROT, 'rb') as f:
    macro('IOprotocolHash', hashlib.sha256(f.read()).hexdigest()[:8], rel(P_IOPROT))
for k, name in (('shim_enc_s', 'IOshimEncms'), ('shim_dec_s', 'IOshimDecms'), ('ecc_enc_s', 'IOeccEncms'),
                ('ecc_dec_s', 'IOeccDecms'), ('bdlc_enc_s', 'IObdlcEncms'), ('bdlc_dec_s', 'IObdlcDecms')):
    macro(name, fnum(io['median_ms'][k], 2), rel(P_IO))
macro('IOshareEnc', fnum(io['shim_share_of_ecc_net_pct']['enc'], 0), rel(P_IO))
macro('IOshareDec', fnum(io['shim_share_of_ecc_net_pct']['dec'], 0), rel(P_IO))
for key, tag in (('speedup_geo_measured', 'GeoMeas'), ('speedup_geo_io_removed', 'GeoAdj'),
                 ('speedup_sum_measured', 'SumMeas'), ('speedup_sum_io_removed', 'SumAdj')):
    for d, D in (('enc', 'Enc'), ('dec', 'Dec')):
        # the geometric mean is undefined when the corrected ECC time of a sequence is not positive (the
        # analysis returns None); that case is reported in the text, never replaced by a number
        if io[key][d] is None:
            assert key == 'speedup_geo_io_removed', key
            continue
        macro('IO' + tag + D, fnum(io[key][d], 1), rel(P_IO))
macro('IOfasterEnc', str(io['sequences_bdlc_faster_io_removed']['enc']), rel(P_IO))
macro('IOfasterDec', str(io['sequences_bdlc_faster_io_removed']['dec']), rel(P_IO))
# descriptive count (from the run's per_map.csv): sequences whose corrected ECC decoding time is not positive
P_IOMAP = os.path.join(IO_RUN, 'per_map.csv')
acc = defaultdict(lambda: [0.0, 0.0])
for r in read_csv(P_IOMAP):
    acc[r['group']][0] += float(r['ecc_dec_s'])
    acc[r['group']][1] += float(r['shim_dec_s'])
macro('IOnonposDec', str(sum(a <= b for a, b in acc.values())), rel(P_IOMAP))
macro('IOgroupsTotal', str(len(acc)), rel(P_IOMAP))

# ---------------------------------------------------------------- consistency with the published ECC-2026 results (B2)
# Published values: tools/published_ecc2026.json (copied from the paper's Tables III and IV, with the source).
P_PUB = os.path.join(HERE, 'published_ecc2026.json')
pub = json.load(open(P_PUB, encoding='utf-8'))['davis']
pub_px = pub['resolution'][0] * pub['resolution'][1]
PUBMAP = [('ECC-2026', 'ecc_direct', 'ECC-2026'), ('HEVC SCC', 'hevc_scc_direct', 'SCM-7.0'),
          ('FLIF', 'flif_u16_e60', 'FLIF'), ('JBIG1', 'jbig_gray_pi', 'JBIG1')]
rows = []
for label, ours, theirs in PUBMAP:
    r = S[(DAVIS, ours)]
    ob = int(r['total_bytes']) / int(r['images_sized'])
    obpp = float(r['micro_bpp'])
    pbpp = 8 * pub['rate_bytes'][theirs] / pub_px
    oe = 1000 * float(r['encode_s_sum']) / int(r['images_timed'])
    od = 1000 * float(r['decode_s_sum']) / int(r['images_timed'])
    rows.append('%s & %s & %s & %s & %s & %s & %s & %s & %s \\\\' % (
        label, fnum(ob, 1), fnum(pub['rate_bytes'][theirs], 1), '%.5f' % obpp, '%.5f' % pbpp, fnum(obpp / pbpp, 3),
        fmag(oe), fmag(1000 * pub['enc_s'][theirs]), fmag(od) + ' / ' + fmag(1000 * pub['dec_s'][theirs])))
    if ours == 'ecc_direct':
        macro('PubECCBytes', fnum(pub['rate_bytes'][theirs], 1), rel(P_PUB))
        macro('OurECCBytes', fnum(ob, 1), rel(P_SUMMARY))
        macro('PubECCbppRatio', fnum(obpp / pbpp, 3), rel(P_SUMMARY) + ' + ' + rel(P_PUB))
        macro('PubECCbppDiff', fnum(100 * (obpp / pbpp - 1), 1), rel(P_SUMMARY) + ' + ' + rel(P_PUB))
        macro('PubECCEncms', fmag(1000 * pub['enc_s'][theirs]), rel(P_PUB))
        macro('PubECCDecms', fmag(1000 * pub['dec_s'][theirs]), rel(P_PUB))
        macro('OurECCEncmsMean', fmag(oe), rel(P_SUMMARY))
        macro('OurECCDecmsMean', fmag(od), rel(P_SUMMARY))
    if ours == 'hevc_scc_direct':
        macro('PubHEVCbppRatio', fnum(obpp / pbpp, 3), rel(P_SUMMARY) + ' + ' + rel(P_PUB))
macro('PubDAVISmaps', fint(pub['maps']), rel(P_PUB))
macro('PubDAVISres', '%d$\\times$%d' % tuple(pub['resolution']), rel(P_PUB))
write('tab_published.tex', r'''\begin{table}[pos=!htbp]
\caption{Our DAVIS 2017 measurements against the values published for the same data set by the authors of ECC-2026 \cite{yang2026ecc} (their Tables III and IV). They used %s maps cropped to %s pixels; we used %s maps at full resolution. Their HEVC SCC was SCM-7.0, ours SCM-8.8; their JBIG1 and FLIF settings are not stated, ours are JBIG1 (Gray) and FLIF 16-bit at default effort. Bytes per map and times are means per map. Our times are net times on one core; theirs are the averages in their Table IV, measured on their machine.}\label{tab:published}
\footnotesize
\begin{tabular*}{\tblwidth}{@{\extracolsep{\fill}}lrrrrrrrr@{}}
\toprule
 & \multicolumn{2}{c}{Bytes per map} & \multicolumn{3}{c}{Bits per pixel} & \multicolumn{2}{c}{Encode (ms)} & Decode (ms) \\
\cmidrule(lr){2-3}\cmidrule(lr){4-6}\cmidrule(lr){7-8}\cmidrule(l){9-9}
Codec & ours & published & ours & published & ratio & ours & published & ours / published \\
\midrule
%s
\bottomrule
\end{tabular*}
\end{table}
''' % (fint(pub['maps']), '%d$\\times$%d' % tuple(pub['resolution']), fint(S[(DAVIS, 'bdlc')]['images_sized']), '\n'.join(rows)),
      [rel(P_SUMMARY), rel(P_PUB)])

# ---------------------------------------------------------------- figures
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

plt.rcParams.update({'pdf.fonttype': 42, 'ps.fonttype': 42, 'font.family': 'DejaVu Sans', 'font.size': 8,
                     'axes.edgecolor': '#c3c2b7', 'axes.linewidth': 0.8, 'xtick.color': '#52514e',
                     'ytick.color': '#52514e', 'axes.labelcolor': '#0b0b0b', 'figure.facecolor': 'white',
                     'axes.facecolor': 'white', 'savefig.facecolor': 'white'})
BLUE, ORANGE, AQUA, GRAY, INK, GRID = '#2a78d6', '#eb6834', '#1baf7a', '#898781', '#0b0b0b', '#e1e0d9'
STYLE = {'BDLC': (BLUE, '*', 120), 'ECC-2026': (ORANGE, 'D', 34), 'Segmentation codecs': (AQUA, '^', 34),
         'Image and video codecs': (GRAY, 's', 26), 'General-purpose compressors': (GRAY, 'o', 26),
         'Earlier codec (RVC)': (GRAY, 'X', 34)}
FIGTXT = json.load(open(os.path.join(HERE, 'figure_labels_uz.json'), encoding='utf-8')) if LANG == 'uz' else {}


# the Uzbek labels are longer: three legend columns and a tight bounding box, so that nothing is cut off
SAVEKW = {} if LANG == 'en' else {'bbox_inches': 'tight', 'pad_inches': 0.03}
NCOL = 4 if LANG == 'en' else 3


def tr(s):
    """Figure text in the language of this build (identity for the manuscript)."""
    return FIGTXT.get(s, s)


def pareto_front(pts):
    """pts: list of (speed, size, codec). Non-dominated: no other point at least as fast and at least as small,
    strictly better in one."""
    front = []
    for s, b, c in pts:
        if not any((s2 >= s and b2 <= b) and (s2 > s or b2 < b) for s2, b2, _ in pts):
            front.append((s, b, c))
    return sorted(front)


def place_labels(ax, items, fig, obstacles, line_xy=None, extra_blocked=()):
    """items: (x, y, text). Greedy placement: for every label try 8 directions at growing distance and keep the
    first spot whose box stays inside the axes and overlaps neither placed labels, nor any marker, nor the
    Pareto line. Every requested label must be placed (assert), so no label is silently dropped."""
    from matplotlib.transforms import Bbox
    fig.canvas.draw()
    rnd = fig.canvas.get_renderer()
    axbox = ax.get_window_extent(rnd)
    to_px = ax.transData.transform
    pts_px = [to_px((ox, oy)) for ox, oy in obstacles]
    mk = 5.0 * fig.dpi / 72                                  # marker half-size in pixels
    blocked = [Bbox([[px - mk, py - mk], [px + mk, py + mk]]) for px, py in pts_px]
    if line_xy:
        lx, ly = line_xy
        for (x0, y0), (x1, y1) in zip(zip(lx, ly), zip(lx[1:], ly[1:])):
            a, b = to_px((x0, y0)), to_px((x1, y1))
            blocked.append(Bbox([[min(a[0], b[0]) - 2, min(a[1], b[1]) - 2], [max(a[0], b[0]) + 2, max(a[1], b[1]) + 2]]))
    blocked.extend(extra_blocked)
    placed = []
    dirs = [(1, 0), (1, 1), (1, -1), (-1, 0), (-1, 1), (-1, -1), (0, 1), (0, -1)]
    for x, y, text in items:
        ok = False
        for radius in (9, 14, 20, 28, 38, 50, 64):
            for dx, dy in dirs:
                kw = dict(xytext=(dx * radius, dy * radius * 0.8), textcoords='offset points', fontsize=7,
                          color=INK, va='center', ha='left' if dx > 0 else ('right' if dx < 0 else 'center'))
                # test with the text alone: an annotation's extent would include the leader line, which
                # always touches the labelled marker
                t = ax.annotate(text, (x, y), **kw)
                bb_ = t.get_window_extent(renderer=rnd).expanded(1.03, 1.2)
                t.remove()
                inside = axbox.x0 <= bb_.x0 and bb_.x1 <= axbox.x1 and axbox.y0 <= bb_.y0 and bb_.y1 <= axbox.y1
                if inside and not any(bb_.overlaps(p) for p in placed) and not any(bb_.overlaps(o) for o in blocked):
                    ax.annotate(text, (x, y), arrowprops=dict(arrowstyle='-', color='#898781', lw=0.5,
                                                              shrinkA=0, shrinkB=4), **kw)
                    placed.append(bb_)
                    ok = True
                    break
            if ok:
                break
        assert ok, 'no free place for label %r' % text


def scatter_figure(kind, fname, label_extra, src, ga=False):
    rows = read_csv(src)
    pts = []
    for r in rows:
        c = r['codec']
        if c in VARIANTS:
            continue
        pts.append((float(r['%s_MPix_s' % kind]), float(r['micro_bpp']), c))
    front = pareto_front(pts)
    # 6.6 x 4.3 in: at 0.8 \textwidth two of these figures and their captions fit on one page of the CAS layout
    fig, ax = plt.subplots(figsize=(6.6, 4.3) if not ga else (6.8, 4.6), dpi=300)
    ax.set_xscale('log')
    ax.set_yscale('log')
    ax.grid(True, which='major', color=GRID, lw=0.5)
    ax.set_axisbelow(True)
    fx = [p[0] for p in front]
    fy = [p[1] for p in front]
    # staircase through the non-dominated points (lower-right is better)
    sx, sy = [], []
    for i, (x, y) in enumerate(zip(fx, fy)):
        if i:
            sx.append(x)
            sy.append(fy[i - 1])
        sx.append(x)
        sy.append(y)
    ax.plot(sx, sy, color='#52514e', lw=0.9, ls='--', zorder=1)
    for cat in ['Image and video codecs', 'General-purpose compressors', 'Earlier codec (RVC)',
                'Segmentation codecs', 'ECC-2026', 'BDLC']:
        col, mk, sz = STYLE[cat]
        xs = [p[0] for p in pts if category(p[2]) == cat]
        ys = [p[1] for p in pts if category(p[2]) == cat]
        ax.scatter(xs, ys, s=sz, marker=mk, c=col, edgecolors='white', linewidths=0.6, zorder=3 if cat != 'BDLC' else 4)
    names = {p[2] for p in front} | ECC | {'bdlc'} | set(label_extra)
    ax.set_xlabel(tr('%s throughput (MPix/s, log scale; higher is better)' % ('Encoding' if kind == 'encode' else 'Decoding')))
    ax.set_ylabel(tr('Compressed size (bits per pixel, log scale; lower is better)'))
    handles = [Line2D([], [], ls='', marker=STYLE[c][1], color=STYLE[c][0], markeredgecolor='white',
                      markersize=7 if c != 'BDLC' else 10, label=tr(c if c != 'BDLC' else 'BDLC (this work)'))
               for c in ['BDLC', 'ECC-2026', 'Segmentation codecs', 'Image and video codecs',
                         'General-purpose compressors', 'Earlier codec (RVC)']]
    handles.append(Line2D([], [], color='#52514e', lw=0.9, ls='--',
                          label=tr('Pareto front of all %d configurations' % (len(competitors) + 1))))
    # legend below the axes, so it can never hide a data point
    leg = ax.legend(handles=handles, loc='upper center', bbox_to_anchor=(0.5, -0.13), fontsize=6.5,
                    frameon=False, ncol=NCOL)
    fig.tight_layout()
    # labels are placed after the layout is final, so their positions are exact; the legend is an obstacle
    items = [(x, y, tr(NAME[c] if c != 'bdlc' else 'BDLC (this work)'))
             for x, y, c in sorted(pts, key=lambda p: (p[2] != 'bdlc', p[1])) if c in names]
    fig.canvas.draw()
    legbox = leg.get_window_extent(fig.canvas.get_renderer())
    obstacles = [(p[0], p[1]) for p in pts]
    place_labels(ax, items, fig, obstacles, line_xy=(sx, sy), extra_blocked=[legbox])
    if ga:
        # the journal prefers TIFF, EPS or PDF for the graphical abstract; PNG is used inside the manuscript
        p = os.path.join(SUB, fname)
        fig.savefig(p, dpi=300, **SAVEKW)
        fig.savefig(p.replace('.png', '.pdf'), **SAVEKW)
        fig.savefig(p.replace('.png', '.tiff'), dpi=300, pil_kwargs={'compression': 'tiff_lzw'}, **SAVEKW)
    else:
        p = os.path.join(FIG, fname)
        fig.savefig(p, **SAVEKW)
        fig.savefig(p.replace('.pdf', '.png'), dpi=300, **SAVEKW)
    plt.close(fig)
    MANIFEST.append((rel(p), [rel(src)]))
    return front


src_enc = os.path.join(RES, 'plot_data', 'size_vs_encode_%s.csv' % DAVIS)
src_dec = os.path.join(RES, 'plot_data', 'size_vs_decode_%s.csv' % DAVIS)
front_enc = scatter_figure('encode', 'fig_pareto_encode.pdf', ['jpegxl10', 'hevc_scc_direct', 'crackle_mo0_zstd19'], src_enc)
front_dec = scatter_figure('decode', 'fig_pareto_decode.pdf', ['jpegxl10', 'hevc_scc_direct', 'crackle_mo0_zstd19'], src_dec)
scatter_figure('encode', 'graphical_abstract.png', [], src_enc, ga=True)
macro('FrontEncNames', andjoin(tex(NAME[c]) if c != 'bdlc' else 'BDLC' for _, _, c in sorted(front_enc, key=lambda p: p[1])), rel(src_enc))
macro('FrontDecNames', andjoin(tex(NAME[c]) if c != 'bdlc' else 'BDLC' for _, _, c in sorted(front_dec, key=lambda p: p[1])), rel(src_dec))
macro('NfrontEnc', str(len(front_enc)), rel(src_enc))
macro('NfrontDec', str(len(front_dec)), rel(src_dec))
tm = read_csv(src_enc)
macro('BppTimedDAVIS', '%.5f' % float([r for r in tm if r['codec'] == 'bdlc'][0]['micro_bpp']), rel(src_enc))
# protocol C: the same figure for COCO-Stuff (encoding) and the decoding front by the same rule
src_enc_c = os.path.join(RES_C, 'plot_data', 'size_vs_encode_%s.csv' % COCO)
src_dec_c = os.path.join(RES_C, 'plot_data', 'size_vs_decode_%s.csv' % COCO)
front_enc_c = scatter_figure('encode', 'fig_pareto_coco.pdf', ['jpegxl10', 'hevc_scc_direct', 'crackle_mo0_zstd19'], src_enc_c)
front_dec_c = pareto_front([(float(r['decode_MPix_s']), float(r['micro_bpp']), r['codec'])
                            for r in read_csv(src_dec_c) if r['codec'] not in VARIANTS])
macro('FrontEncNamesCOCO', andjoin(tex(NAME[c]) if c != 'bdlc' else 'BDLC' for _, _, c in sorted(front_enc_c, key=lambda p: p[1])), rel(src_enc_c))
macro('FrontDecNamesCOCO', andjoin(tex(NAME[c]) if c != 'bdlc' else 'BDLC' for _, _, c in sorted(front_dec_c, key=lambda p: p[1])), rel(src_dec_c))
macro('BppTimedCOCO', '%.5f' % float([r for r in read_csv(src_enc_c) if r['codec'] == 'bdlc'][0]['micro_bpp']), rel(src_enc_c))

# bar chart: compressed size, all 6,208 DAVIS maps
src = os.path.join(RES, 'plot_data', 'size_%s.csv' % DAVIS)
rows = [r for r in read_csv(src) if r['codec'] not in VARIANTS]
rows.sort(key=lambda r: float(r['micro_bpp']))
fig, ax = plt.subplots(figsize=(6.6, 7.0), dpi=300)
y = np.arange(len(rows))[::-1]
# dot plot: on a log axis a bar's length would not be proportional to its value
for yy, r in zip(y, rows):
    col, mk, sz = STYLE[category(r['codec'])]
    ax.axhline(yy, color=GRID, lw=0.5, zorder=1)
    ax.scatter([float(r['micro_bpp'])], [yy], s=sz * 1.2, marker=mk, c=col, edgecolors='white', linewidths=0.6,
               zorder=3)
ax.set_yticks(y)
ax.set_yticklabels([tr('BDLC (this work)' if r['codec'] == 'bdlc' else NAME[r['codec']]) for r in rows], fontsize=7)
for t, r in zip(ax.get_yticklabels(), rows):
    if r['codec'] == 'bdlc':
        t.set_fontweight('bold')
ax.set_xscale('log')
ax.grid(True, axis='x', which='both', color=GRID, lw=0.5)
ax.set_axisbelow(True)
ax.set_xlabel(tr('Compressed size (bits per pixel, log scale; lower is better)'))
ax.set_ylim(-0.7, len(rows) - 0.3)
handles = [Line2D([], [], ls='', marker=STYLE[c][1], color=STYLE[c][0], markeredgecolor='white',
                  markersize=7 if c != 'BDLC' else 10, label=tr(c if c != 'BDLC' else 'BDLC (this work)'))
           for c in ['BDLC', 'ECC-2026', 'Segmentation codecs', 'Image and video codecs',
                     'General-purpose compressors', 'Earlier codec (RVC)']]
ax.legend(handles=handles, loc='upper center', bbox_to_anchor=(0.4, -0.07), fontsize=6.5, frameon=False, ncol=3)
fig.tight_layout()
p = os.path.join(FIG, 'fig_size.pdf')
fig.savefig(p, **SAVEKW)
fig.savefig(p.replace('.pdf', '.png'), dpi=300, **SAVEKW)
plt.close(fig)
MANIFEST.append((rel(p), [rel(src)]))
assert [r['images'] if 'images' in r else None for r in rows]  # source rows exist

# stacked bars: where BDLC spends its information
SEGC = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4']
fig, ax = plt.subplots(figsize=(6.6, 2.7), dpi=300)
dsl = [DAVIS] + CTC + [COCO]
for i, ds in enumerate(dsl[::-1]):
    left = 0
    for j, v in enumerate(shares[ds]):
        ax.barh(i, v, left=left, color=SEGC[j], edgecolor='white', linewidth=1.0, height=0.62)
        if v >= 7:
            ax.text(left + v / 2, i, '%d%%' % round(v), ha='center', va='center', fontsize=6.5,
                    color='#0b0b0b' if SEGC[j] == '#eda100' else 'white')
        left += v
ax.set_yticks(range(len(dsl)))
ax.set_yticklabels([tr(SCOPE_NAME[d]) for d in dsl[::-1]], fontsize=7)
ax.set_xlim(0, 100)
ax.set_xlabel(tr('Share of the model information content of BDLC (%)'))
ax.legend([plt.Rectangle((0, 0), 1, 1, color=c) for c in SEGC], [tr(n) for n, _ in COMP], fontsize=6.5, frameon=False,
          loc='upper center', bbox_to_anchor=(0.5, -0.32), ncol=3)
for s in ('top', 'right'):
    ax.spines[s].set_visible(False)
fig.tight_layout()
p = os.path.join(FIG, 'fig_bit_shares.pdf')
fig.savefig(p, **SAVEKW)
fig.savefig(p.replace('.pdf', '.png'), dpi=300, **SAVEKW)
plt.close(fig)
MANIFEST.append((rel(p), [rel(P_BB), rel(P_BB_C)]))

# ---------------------------------------------------------------- write numbers.tex and the manifest
p = os.path.join(OUT, 'numbers.tex')
with open(p, 'w', encoding='utf-8', newline='\n') as f:
    f.write('% Generated by paper_CEE/tools/make_paper_assets.py. Do not edit by hand.\n')
    f.write('% Every value below is computed from the files named after it (runs 20261029_081034_test_B and 20261030_134701_test_C).\n')
    seen = set()
    for name, value, source in MACROS:
        assert name not in seen, name
        seen.add(name)
        f.write('\\newcommand{\\%s}{%s}%% %s\n' % (name, value, source))
MANIFEST.append((rel(p), sorted({s for _, _, s in MACROS})))
with open(os.path.join(OUT if os.environ.get('BDLC_PAPER_OUT') else HERE, 'assets_manifest.json'), 'w', encoding='utf-8') as f:
    json.dump({'runs': [rel(RUN), rel(RUN_C)], 'outputs': [{'file': o, 'sources': s} for o, s in MANIFEST],
               'macros': [{'name': n, 'value': v, 'source': s} for n, v, s in MACROS]}, f, indent=1)
print('macros:', len(MACROS), '| tables:', len([m for m in MANIFEST if '/tables/' in m[0]]),
      '| figures:', len([m for m in MANIFEST if m[0].endswith(('.pdf', '.png'))]))
