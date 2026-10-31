Pre-registered hypotheses B1-B4 (PROTOKOL_B_UZ.md). delta_pct > 0 means BDLC smaller.

| Scope | Hypothesis | Maps | Clusters | Clusters BDLC better | Estimate | 95% CI | p (sign) | p (Holm) |
|---|---|---|---|---|---|---|---|---|
| COCO-Stuff_val2017 | B1 size vs ECC (oracle of ecc_direct+ecc_pi), two-sided | 5000 | 5000 | 1839 | -4.47 | [-4.85, -4.10] | 0.0000 | 0.0000 |
| COCO-Stuff_val2017 | B2 size vs best non-ECC competitor (33 configurations), one-sided | 5000 | 5000 | 4209 | 10.10 | [9.79, 10.41] | 0.0000 | 0.0000 |
| COCO-Stuff_val2017 | B3 faster than ecc_direct in encode and decode, one-sided (intersection-union) | 1000 | 1000 | 1000 enc / 1000 dec | 22.809 / 10.780 |  | 0.0000 | 0.0000 |
