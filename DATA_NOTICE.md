# Data sources and licences

## Cell Tracking Challenge (included)

The folders `data/` (development maps) and `BDLC/data_test/` (test maps) contain ground-truth segmentation maps (`*_GT/SEG/man_seg*.tif`) of the Cell Tracking Challenge (CTC) training datasets. The files were extracted byte for byte from the CTC training-set archives. The test archives were downloaded from the official CTC copies on Zenodo; for the development archives the download script lists the same Zenodo copies first and the CTC server second. These Zenodo records are published under the Creative Commons Attribution 4.0 International licence (CC BY 4.0):

| Dataset | Used as | Zenodo DOI | Licence |
|---|---|---|---|
| DIC-C2DH-HeLa | development | 10.5281/zenodo.15608194 | CC BY 4.0 |
| PhC-C2DH-U373 | development | 10.5281/zenodo.15608252 | CC BY 4.0 |
| Fluo-N2DH-GOWT1 | test | 10.5281/zenodo.15608211 | CC BY 4.0 |
| PhC-C2DL-PSC | test | 10.5281/zenodo.15608232 | CC BY 4.0 |
| Fluo-N2DH-SIM+ (simulated) | test, reported separately | 10.5281/zenodo.15608207 | CC BY 4.0 |

Please cite the Cell Tracking Challenge when using these maps:

- V. Ulman et al., "An objective comparison of cell-tracking algorithms," *Nature Methods* 14, 1141–1152 (2017).
- M. Maška et al., "The Cell Tracking Challenge: 10 years of objective benchmarking," *Nature Methods* 20, 1010–1020 (2023).

## DAVIS 2017 (not included)

The DAVIS 2017 trainval 480p annotations are not redistributed, because the DAVIS README states two different licences (CC BY 4.0 under "Credits" and CC BY-NC 4.0 under "Terms of Use"). The source URL and SHA-256 of the archive are in `BDLC/downloads/DAVIS2017/ACQUISITION.json`, and `BDLC/data_B/DAVIS2017/INVENTORY.csv` lists the SHA-256 of every map. Please cite:

- J. Pont-Tuset et al., "The 2017 DAVIS Challenge on Video Object Segmentation," arXiv:1704.00675 (2017).
- F. Perazzi et al., "A Benchmark Dataset and Evaluation Methodology for Video Object Segmentation," CVPR 2016.

## Third-party software (not included)

Source archives of ECC-2026, HM-16.21+SCM-8.8, JBIG-KIT 2.1, FLIF 0.4 and Compresso are not included. Their URLs, versions or commits, licences and SHA-256 hashes are in `BDLC/downloads/baselines/ACQUISITION.json` and `BDLC/downloads/baselines/INVENTORY.csv`.
