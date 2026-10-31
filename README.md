# BDLC: boundary-displacement lossless coding of segmentation label maps

This repository contains the code, the frozen codec, the experiment protocols and the measured results of the two runs behind the manuscript

> *Fast Lossless Compression of Multi-Label Segmentation Maps by Boundary-Displacement Coding: An Empirically Speed–Size Pareto-Optimal Codec* (manuscript in preparation).

BDLC is a lossless codec for 2D label maps (8- or 16-bit segmentation masks). It codes each row as runs. A run's label is predicted from two candidates in the row above, and the run's end is coded as a displacement from the matching boundary in the row above. All decisions are coded with context-adaptive binary range coding.

Every number below is copied from a file in this repository; the file is named next to it.

## Main result (protocol B, DAVIS 2017 trainval 480p)

The experiment measured 41 codec configurations (BDLC, five BDLC variants and 35 competitor configurations) on 6,477 maps. The primary cohort is DAVIS 2017 (6,208 maps, 90 video sequences). Sizes were measured on all maps. Speed was measured on 900 DAVIS maps (10 frames per sequence), on one pinned CPU core, with 3 repeats per measurement.

Source: `BDLC/runs/20261029_081034_test_B/results/tables/summary_by_dataset.csv` (scope `DAVIS2017_480p`).

| Codec | Size (bits per pixel, pooled) | Encode (MPix/s) | Decode (MPix/s) |
|---|---:|---:|---:|
| **BDLC** | 0.008090 | 1770.7 | 2443.8 |
| ECC-2026 | 0.007366 | 102.2 | 283.4 |
| ECC-2026 (rank map) | 0.007527 | 78.4 | 188.2 |
| Crackle mo0 + zstd -19 | 0.011251 | 361.4 | 755.0 |
| JPEG-LS | 0.046858 | 2663.3 | 5148.9 |
| Zstandard -3 | 0.050506 | 3577.2 | 5393.2 |

ECC-2026 produces smaller files than BDLC. JPEG-LS and Zstandard -3 are faster than BDLC but produce files about six times larger. The full table for all 41 configurations is in `results/tables/` and `results/paper/tables/`.

### Pre-registered hypotheses

The hypotheses, tests and decision rules were fixed in `BDLC/PROTOKOL_B_UZ.md` and `BDLC/protocol_B.json` before the run. Clusters are the 90 video sequences; Δ is the cluster-mean log ratio expressed in percent (positive means BDLC is smaller). Source: `results/statistics/protocol_B_tests.csv` and `results/statistics/pareto_B4.csv`.

| Test | Question | Result on DAVIS 2017 |
|---|---|---|
| B1 | Size versus ECC-2026 (best of its two modes per map), two-sided | Δ = −10.20 % (95 % CI −11.12 to −9.22); BDLC smaller in 2 of 90 sequences. **ECC-2026 is smaller.** |
| B2 | Size versus the best of the 33 other competitor configurations per map, one-sided | Δ = +33.12 % (95 % CI 30.44 to 35.61); BDLC smaller in 87 of 90 sequences |
| B3 | Faster than ECC-2026 in both encoding and decoding, one-sided | Encode 17.15×, decode 8.63× (geometric mean over sequences); faster in 90 of 90 sequences in both |
| B4 | Is any configuration smaller **and** faster in encoding **and** in decoding in more than half of the sequences? | No configuration (0 of 35) |

### Verification

- Experiment status: `COMPLETE`, 0 harness failures (`runs/20261029_081034_test_B/status.json`, `failures.json`).
- 265,557 (configuration, map) pairs were compressed. Every stream was decoded in a separate process and compared with the source pixels by SHA-256 (`verification/`).
- 47,929 timed pairs. Each stream written in the timing phase has the same SHA-256 as the stream verified in the size phase.
- Report status: `COMPLETE`, 162 generated files, 0 failed checks (`results/reports/status.json`, `results/reports/artifact_manifest.json`).

## Second run (protocol C, COCO-Stuff val2017)

Protocol C applies the same harness, configurations, settings and hypotheses to the 5,000 semantic maps of COCO-Stuff val2017. Its protocol file differs from protocol B only in its date, the input and manifest hashes, the number of timed maps and the hash of the script that converted the maps (`BDLC/protocol_C.json`, SHA-256 `1c8570c6…`; plan in `BDLC/PROTOKOL_C_UZ.md`). Protocol C was written **after** the results of protocol B were known; its hypotheses C1–C4 repeat B1–B4 without change. COCO images are independent photographs, so every map is its own cluster. Speed was measured on every fifth map in id order (1,000 maps).

Source: `BDLC/runs/20261030_134701_test_C/results/tables/summary_by_dataset.csv` (scope `COCO-Stuff_val2017`).

| Codec | Size (bits per pixel, pooled) | Encode (MPix/s) | Decode (MPix/s) |
|---|---:|---:|---:|
| **BDLC** | 0.034242 | 957.2 | 1196.1 |
| ECC-2026 | 0.032848 | 41.2 | 109.7 |
| ECC-2026 (rank map) | 0.033284 | 42.5 | 98.8 |
| Crackle mo0 + zstd -19 | 0.037517 | 253.0 | 473.3 |
| JPEG-LS | 0.187554 | 1412.7 | 1825.0 |
| Zstandard -3 | 0.135552 | 2418.7 | 3864.7 |
| Zstandard -19 | 0.099412 | 13.5 | 3472.5 |

The harness names its test files after protocol B; in this run, rows B1–B4 of `results/statistics/protocol_B_tests.csv` and `results/statistics/pareto_B4.csv` are the hypotheses C1–C4.

| Test | Result on COCO-Stuff val2017 (5,000 clusters) |
|---|---|
| C1 | Δ = −4.47 % (95 % CI −4.85 to −4.10); BDLC smaller on 1,839 of 5,000 maps. **ECC-2026 is smaller.** |
| C2 | Δ = +10.10 % (95 % CI 9.79 to 10.41); BDLC smaller on 4,209 of 5,000 maps |
| C3 | Encode 22.81×, decode 10.78× (geometric mean over maps); faster on 1,000 of 1,000 timed maps in both |
| C4 | No configuration (0 of 35) is smaller and faster in both directions on any of the 1,000 timed maps |

JPEG-LS, Zstandard -3 and (in decoding) Zstandard -19 are faster than BDLC but produce files 2.9 to 5.5 times larger.

### Verification

- Experiment status: `COMPLETE`, 0 harness failures (`runs/20261030_134701_test_C/status.json`, `failures.json`).
- 205,000 (configuration, map) pairs were compressed; every stream was decoded in a separate process and compared with the source pixels by SHA-256 (`verification/`).
- 41,000 timed pairs; each stream written in the timing phase has the same SHA-256 as the stream verified in the size phase.
- Size phase 36 minutes, timing phase 3 hours 42 minutes (`status.json`).
- Report status: `PARTIAL`, 46 generated files, 1 failed check (`results/reports/status.json`, `results/reports/errors.md`). The report's self-check could not read back `statistics/virtual_best.csv`, because one column lists values for all 5,000 clusters and is longer than the default field limit of Python's `csv` module (131,072 characters). The file itself is complete: read with a larger limit (`csv.field_size_limit`), its C1 and C2 values equal those in `protocol_B_tests.csv`. `BDLC/paper_CEE/tools/make_paper_assets.py` checks this. The measurements are not affected.

## Post-hoc I/O calibration (DAVIS 2017)

ECC-2026 runs as a command-line program and exchanges its data with the harness through files; only the fixed cost of a call is subtracted from its times. To bound the remaining cost, a post-hoc run with its own hash-locked protocol (`BDLC/runs/20261030_175722_io_calibration/protocol_IO.json`, written by `BDLC/posthoc/io_calibration/prepare.py` before anything was timed) measured, in one session and on the 900 DAVIS timing maps of protocol B: ECC-2026 with its real programs, ECC-2026 with pass-through programs that only copy their input file to their output file (`BDLC/posthoc/io_calibration/bin/`), and BDLC. Source: `runs/20261030_175722_io_calibration/summary.json` (`posthoc/io_calibration/analyze.py`).

- The pass-through took 0.77 ms (encoding) and 0.19 ms (decoding) per map (medians), 25 % and 40 % of the net ECC-2026 times of the same session.
- Encoding: BDLC was 19.3 times faster as measured and 14.4 times faster with the pass-through time subtracted (ratio of summed times), and faster in 90 of 90 sequences.
- Decoding: 9.2 times as measured and 5.5 times with the subtraction, faster in 79 of 90 sequences.
- The pass-through stores the whole map as its "stream", so it moves more data through files than ECC-2026 does; the subtraction over-corrects.

## Repository layout

```
START_B.ps1, START_C.ps1    one command each (Windows PowerShell) that runs protocol B or C in the container
real_manifest.csv           development maps; the protocols check that no test map duplicates them
data/                       development maps (Cell Tracking Challenge, CC BY 4.0, see DATA_NOTICE.md)
BDLC/
  bdlc/                     the codec (frozen v1; hashes in freeze.json)
  legacy_rvc.py             earlier codec, included as a baseline
  bench/                    benchmark harness and the automatic report generator (make_reports.py)
  tools/                    data preparation and development tools (build_manifest_B.py, build_manifest_C.py, ...)
  tests/                    unit tests of the codec
  docker/                   container build scripts, run_B.sh / run_C.sh, the ECC patch, build logs and binary hashes
  downloads/                source URLs and SHA-256 of every external download (no archives)
  data_test/                CTC test maps (CC BY 4.0, see DATA_NOTICE.md)
  data_B/DAVIS2017/INVENTORY.csv     per-map SHA-256 of the DAVIS maps (the maps themselves are not included)
  data_C/COCO-Stuff/INVENTORY.csv    per-map SHA-256 of the COCO-Stuff maps (the maps themselves are not included)
  manifest_B.csv, manifest_C.csv     the inputs of protocols B (6,477 maps) and C (5,000 maps)
  protocol_B.json, protocol_C.json   protocol files: code hashes, input hashes, codecs, parameters, platform
  PROTOKOL_B_UZ.md, PROTOKOL_C_UZ.md pre-registered protocols (Uzbek)
  METOD_VA_MATEMATIKA_UZ.md method specification and proofs (Uzbek)
  posthoc/                  post-hoc I/O calibration (io_calibration/) and summarize_shards.py
  paper_CEE/tools/          make_paper_assets.py: every number, table and figure of the manuscript
  runs/20261029_081034_test_B/   protocol B
  runs/20261030_134701_test_C/   protocol C
    status.json, failures.json, not_applicable.json, unavailable.json
    raw_size/               measured stream sizes (size phase); shards_meta.json: worker records of the size phase
    raw/                    measured times (timing phase)
    verification/           independent decode checks
    byte_breakdown.csv      where BDLC spends its bits, per map
    coldstart/              cold-start measurements
    provenance/             frozen-code record, input audit, artifact hashes
    results/                tables, statistics, plot data, figures, paper tables, reports
  runs/20261030_175722_io_calibration/   post-hoc I/O calibration: protocol, tasks, raw times, per-map results, summary
```

Documents ending in `_UZ.md` are in Uzbek. The English manuscript describes the same method and protocols.

## Using the results without re-running the experiment

All tables, statistics and figures of a run can be regenerated from the measured files in this repository:

```
python BDLC/bench/make_reports.py BDLC/runs/20261029_081034_test_B --out regenerated_results
python BDLC/bench/make_reports.py BDLC/runs/20261030_134701_test_C --out regenerated_results_C
```

It needs Python 3.14 with `numpy` and `matplotlib` (versions in `BDLC/requirements.txt`). The script reads `raw_size/`, `raw/`, `verification/`, `coldstart/`, `provenance/` and the status files, and checks every generated file against the primary data. For run C it reports `PARTIAL` for the reason given above.

We ran the first command on Windows 11 from this repository's files; the committed results were generated in the Linux container. All 36 CSV files agreed to within 2.3×10⁻¹⁶ (relative), the last digit of a double-precision number. The only other differences were Wilcoxon p-values from the normal approximation below 10⁻¹⁵, which are at the limit of double precision (for example 2.2×10⁻¹⁶ on Linux and 0 on Windows); they should be read as p < 10⁻¹⁵. Text tables may differ in line endings.

Every number, table and figure of the manuscript is produced from these files by

```
python -I BDLC/paper_CEE/tools/make_paper_assets.py
```

It writes `numbers.tex`, the tables and the figures into `BDLC/paper_CEE/overleaf/` (the manuscript text itself is not part of this repository) and checks the statements of the text with assertions; `BDLC/paper_CEE/tools/assets_manifest.json` lists every output with the files it was computed from. It needs `numpy`, `matplotlib` and `tifffile`, and the COCO-Stuff maps (see below), whose classes it counts.

## Re-running the experiment

The runs used three Docker images built on 2026-10-29 by running the scripts in `BDLC/docker/` in containers and committing the results (`BDLC/docker/README_UZ.md` lists the image digests):

1. `bdlc-baselines-env:2026-10-29`: `BDLC/docker/Dockerfile` (pinned Ubuntu 24.04 base and compiler packages; all installed versions in `docker/packages.tsv`).
2. `bdlc-baselines:2026-10-29`: `BDLC/docker/build_baselines.sh` builds ECC-2026, HEVC SCC (HM-16.21+SCM-8.8), JBIG-KIT 2.1, FLIF 0.4 and Compresso from the source archives listed in `BDLC/downloads/baselines/INVENTORY.csv` (URL and SHA-256). The only source change is `docker/patches/ecc_ub_fixes.patch`, a three-line fix of undefined behaviour in ECC-2026 (missing return values and a buffer over-read) without which the GCC 13 `-O2` build crashed; details in `docker/README_UZ.md`, section 3.
3. `bdlc-bench:2026-10-29`: `BDLC/docker/setup_python.sh` adds Python 3.14.4 (python-build-standalone, SHA-256 in `downloads/python/SHA256SUMS`) and the pinned packages of `BDLC/requirements.txt`.

A rebuild may pull newer Ubuntu patch versions; compare with `docker/packages.tsv`.

Input data:

- **DAVIS 2017 trainval 480p.** Download `DAVIS-2017-trainval-480p.zip` from the source in `BDLC/downloads/DAVIS2017/ACQUISITION.json` and check its SHA-256 (`e3d0b5b77c3d031b000a19e0e25e3e2cac65d183755601bc2cf066df1a2aa492`). Then run `python -I BDLC/tools/build_manifest_B.py <path to the zip>`. It writes the maps to `BDLC/data_B/` and rewrites `BDLC/manifest_B.csv` and `BDLC/data_B/DAVIS2017/INVENTORY.csv`; both should come out identical to the committed files (check with `git diff`). The harness then checks every map against the hashes in `protocol_B.json`.
- **COCO-Stuff val2017.** Download `stuffthingmaps_trainval2017.zip` from the source in `BDLC/downloads/COCO-Stuff/ACQUISITION.json` and check its SHA-256 (`da7f213d6a581bd6912a957573d7b4e5061de0d41f733bb27249b0fa981239d7`). Then run `python -I BDLC/tools/build_manifest_C.py <path to the zip>`. It writes the 5,000 validation maps to `BDLC/data_C/` and rewrites `BDLC/manifest_C.csv` and `BDLC/data_C/COCO-Stuff/INVENTORY.csv`; both should come out identical to the committed files (check with `git diff`). The harness checks every map against the hashes in `protocol_C.json`.
- **Cell Tracking Challenge maps** are included (`data/`, `BDLC/data_test/`).

Then run a protocol from the repository root:

```
.\START_B.ps1
.\START_C.ps1
```

The harness compares every code file and every input file with the protocol file and refuses to start if anything differs. On the original machine (Intel Core i7-13700F, Docker Desktop with WSL2) protocol B took about 6 hours (about 1 hour for the size phase and about 5 hours for the timing phase) and protocol C about 4 hours 20 minutes.

## What is not included

- **DAVIS and COCO-Stuff maps.** The DAVIS README gives two different licences (CC BY 4.0 and CC BY-NC 4.0), so those maps are not redistributed; the COCO-Stuff maps are available from their authors (CC BY 4.0). `build_manifest_B.py` and `build_manifest_C.py` recreate them from the official archives.
- **Third-party source code and binaries** (ECC-2026, HM/SCM, JBIG-KIT, FLIF, Compresso). Only their URLs, SHA-256 hashes, build scripts and the ECC patch are included.
- **The compressed streams** of both runs (about 265,000 and 205,000 files) and the streams of the I/O calibration. Their SHA-256 hashes are in `provenance/artifact_hashes.json` and in the measurement files; the streams will be published as a separate archive.
- **The size-phase shard files** (`raw_size/shards/`, `verification/shards/`). The harness merged them into `raw_size/<codec>.json` and `verification/<codec>.json`; `BDLC/posthoc/summarize_shards.py` checked that every record of every shard is in the merged files and wrote the remaining shard fields (worker, start and end time) to `raw_size/shards_meta.json`.
- **Worker logs and task lists** of the runs (`logs/`, `tasks/`), except the task lists of the I/O calibration, whose hashes are part of its protocol.
- **Earlier runs** (development run and the first test cohort on Windows). They are described in the manuscript.

## Data licences and citations

See `DATA_NOTICE.md`.

## Licence

- Code in this repository: MIT licence (`LICENSE`).
- Data: the Cell Tracking Challenge maps keep their CC BY 4.0 licence (`DATA_NOTICE.md`).
- `BDLC/docker/patches/ecc_ub_fixes.patch` modifies ECC-2026, which is distributed under its own BSD licence (InterDigital); see `BDLC/downloads/baselines/ACQUISITION.json`.
