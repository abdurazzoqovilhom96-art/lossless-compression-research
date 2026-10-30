# BDLC: boundary-displacement lossless coding of segmentation label maps

This repository contains the code, the frozen codec, the experiment protocol and the measured results behind the manuscript

> *Fast Lossless Compression of Multi-Label Segmentation Maps by Boundary-Displacement Coding: An Empirically Speed–Size Pareto-Optimal Codec* (manuscript in preparation).

BDLC is a lossless codec for 2D label maps (8- or 16-bit segmentation masks). It codes each row as runs. A run's label is predicted from two candidates in the row above, and the run's end is coded as a displacement from the matching boundary in the row above. All decisions are coded with context-adaptive binary range coding.

Every number below is copied from a CSV file in this repository; the file is named next to it.

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

## Repository layout

```
START_B.ps1                 one command (Windows PowerShell) that runs protocol B in the container
real_manifest.csv           development maps; protocol B checks that no test map duplicates them
data/                       development maps (Cell Tracking Challenge, CC BY 4.0, see DATA_NOTICE.md)
BDLC/
  bdlc/                     the codec (frozen v1; hashes in freeze.json)
  legacy_rvc.py             earlier codec, included as a baseline
  bench/                    benchmark harness and the automatic report generator (make_reports.py)
  tools/                    data preparation and development tools
  tests/                    unit tests of the codec
  docker/                   container build scripts, the ECC patch, build logs and binary hashes
  downloads/                source URLs and SHA-256 of every external download (no archives)
  data_test/                CTC test maps (CC BY 4.0, see DATA_NOTICE.md)
  data_B/DAVIS2017/INVENTORY.csv   per-map SHA-256 of the DAVIS maps (the maps themselves are not included)
  manifest_B.csv            the 6,477 inputs of protocol B
  protocol_B.json           protocol file: code hashes, input hashes, codecs, parameters, platform
  PROTOKOL_B_UZ.md          pre-registered protocol (Uzbek)
  METOD_VA_MATEMATIKA_UZ.md method specification and proofs (Uzbek)
  runs/20261029_081034_test_B/
    status.json, failures.json, not_applicable.json, unavailable.json
    raw_size/               measured stream sizes (size phase)
    raw/                    measured times (timing phase)
    verification/           independent decode checks
    byte_breakdown.csv      where BDLC spends its bits, per map
    coldstart/              cold-start measurements
    provenance/             frozen-code record, input audit, artifact hashes
    results/                tables, statistics, plot data, figures, paper tables, reports
```

Documents ending in `_UZ.md` are in Uzbek. The English manuscript will describe the same method and protocol.

## Using the results without re-running the experiment

All tables, statistics and figures can be regenerated from the measured files in this repository:

```
python BDLC/bench/make_reports.py BDLC/runs/20261029_081034_test_B --out regenerated_results
```

It needs Python 3.14 with `numpy` and `matplotlib` (versions in `BDLC/requirements.txt`). The script reads `raw_size/`, `raw/`, `verification/`, `coldstart/`, `provenance/` and the status files, and checks every generated file against the primary data.

We ran this command on Windows 11 from this repository's files; the committed results were generated in the Linux container. All 36 CSV files agreed to within 2.3×10⁻¹⁶ (relative), the last digit of a double-precision number. The only other differences were Wilcoxon p-values from the normal approximation below 10⁻¹⁵, which are at the limit of double precision (for example 2.2×10⁻¹⁶ on Linux and 0 on Windows); they should be read as p < 10⁻¹⁵. Text tables may differ in line endings.

## Re-running the experiment

The run used three Docker images built on 2026-10-29 by running the scripts in `BDLC/docker/` in containers and committing the results (`BDLC/docker/README_UZ.md` lists the image digests):

1. `bdlc-baselines-env:2026-10-29`: `BDLC/docker/Dockerfile` (pinned Ubuntu 24.04 base and compiler packages; all installed versions in `docker/packages.tsv`).
2. `bdlc-baselines:2026-10-29`: `BDLC/docker/build_baselines.sh` builds ECC-2026, HEVC SCC (HM-16.21+SCM-8.8), JBIG-KIT 2.1, FLIF 0.4 and Compresso from the source archives listed in `BDLC/downloads/baselines/INVENTORY.csv` (URL and SHA-256). The only source change is `docker/patches/ecc_ub_fixes.patch`, a three-line fix of undefined behaviour in ECC-2026 (missing return values and a buffer over-read) without which the GCC 13 `-O2` build crashed; details in `docker/README_UZ.md`, section 3.
3. `bdlc-bench:2026-10-29`: `BDLC/docker/setup_python.sh` adds Python 3.14.4 (python-build-standalone, SHA-256 in `downloads/python/SHA256SUMS`) and the pinned packages of `BDLC/requirements.txt`.

A rebuild may pull newer Ubuntu patch versions; compare with `docker/packages.tsv`.

Input data:

- **DAVIS 2017 trainval 480p.** Download `DAVIS-2017-trainval-480p.zip` from the source in `BDLC/downloads/DAVIS2017/ACQUISITION.json` and check its SHA-256 (`e3d0b5b77c3d031b000a19e0e25e3e2cac65d183755601bc2cf066df1a2aa492`). Then run `python -I BDLC/tools/build_manifest_B.py <path to the zip>`. It writes the maps to `BDLC/data_B/` and rewrites `BDLC/manifest_B.csv` and `BDLC/data_B/DAVIS2017/INVENTORY.csv`; both should come out identical to the committed files (check with `git diff`). The harness then checks every map against the hashes in `protocol_B.json`.
- **Cell Tracking Challenge maps** are included (`data/`, `BDLC/data_test/`).

Then run protocol B from the repository root:

```
.\START_B.ps1
```

The harness compares every code file and every input file with `protocol_B.json` and refuses to start if anything differs. On the original machine (Intel Core i7-13700F, Docker Desktop with WSL2) the run took about 6 hours: about 1 hour for the size phase and about 5 hours for the timing phase.

## What is not included

- **DAVIS maps.** The DAVIS README gives two different licences (CC BY 4.0 and CC BY-NC 4.0), so the maps are not redistributed here; `build_manifest_B.py` recreates them from the official archive.
- **Third-party source code and binaries** (ECC-2026, HM/SCM, JBIG-KIT, FLIF, Compresso). Only their URLs, SHA-256 hashes, build scripts and the ECC patch are included.
- **The compressed streams** of protocol B (about 265,000 files). They will be published as a separate archive.
- **Earlier runs** (development run and the first test cohort on Windows). They are described in the manuscript.

## Data licences and citations

See `DATA_NOTICE.md`.

## Licence

- Code in this repository: MIT licence (`LICENSE`).
- Data: the Cell Tracking Challenge maps keep their CC BY 4.0 licence (`DATA_NOTICE.md`).
- `BDLC/docker/patches/ecc_ub_fixes.patch` modifies ECC-2026, which is distributed under its own BSD licence (InterDigital); see `BDLC/downloads/baselines/ACQUISITION.json`.
