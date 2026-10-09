# SP3 orbit files

Exported with `Opus_Fork.export write` (model-aware frame, QA re-read of every position; `deliverables/make_sp3.sh`). GPS satellite centre of mass, IGc20, GPS time, 15-minute cadence, positions only (clocks are the missing value 999999.999999), accuracy codes 0 (unknown). `RAP`/`FIN` in a name is this project's local category, not an IGS product class. The SP3 files are not in git.

## default_25st

Best rapid-candidate configuration: the adopted default (ECOM5, Earth radiation and antenna thrust, IERS 2010 sub-daily EOP, elevation weighting), 25 stations, no tropospheric gradients. Inputs are plausibly rapid, but these files were made retrospectively.

| File | SHA-256 | Source solution | QA |
|---|---|---|---|
| `OPUS0OPSRAP_20260606_default_25st.SP3` | `67ce754df14d96a4…` | `20260930T012728Z-fit-U-elw13-0606/lin2-solve` | passed |
| `OPUS0OPSRAP_20260620_default_25st.SP3` | `09f78ec2dfa3a08e…` | `20260929T233503Z-fit-U-elw13-0620/lin2-solve` | passed |
| `OPUS0OPSRAP_20260623_default_25st.SP3` | `ee45e1f27de4b025…` | `20261001T012217Z-fit-U-elw13-0623r/lin3-solve` | passed |
| `OPUS0OPSRAP_20260706_default_25st.SP3` | `192cd258b5389988…` | `20260930T234445Z-fit-U-elw13-0706/lin2-solve` | passed |
| `OPUS0OPSRAP_20260723_default_25st.SP3` | `6934c17b59902d2e…` | `20260930T220757Z-fit-U-elw13-0723/lin2-solve` | passed |

## S17_nga_like

17 stations placed like NGA's monitor network (network test S17), default + TU Wien GRAD operational gradients. Final latency.

| File | SHA-256 | Source solution | QA |
|---|---|---|---|
| `OPUS0OPSFIN_20260606_S17_nga_like.SP3` | `fcd0ff09e0c8c80d…` | `20261005T220139Z-fit-S17-op-0606/lin2-solve` | passed |
| `OPUS0OPSFIN_20260620_S17_nga_like.SP3` | `921c900fd331bb5b…` | `20261005T230105Z-fit-S17-op-0620/lin3-solve` | passed |
| `OPUS0OPSFIN_20260623_S17_nga_like.SP3` | `958615e4d503dfb9…` | `20261006T002221Z-fit-S17-op-0623/lin2-solve` | passed |
| `OPUS0OPSFIN_20260706_S17_nga_like.SP3` | `7040961cd6f454e5…` | `20261006T010650Z-fit-S17-op-0706/lin2-solve` | passed |
| `OPUS0OPSFIN_20260723_S17_nga_like.SP3` | `df429117242d3b27…` | `20261006T220323Z-fit-S17-op-0723/lin2-solve` | passed |

## S50_doubled

50 stations (network test S50, ambiguity elimination), default + TU Wien GRAD operational gradients. Final latency.

| File | SHA-256 | Source solution | QA |
|---|---|---|---|
| `OPUS0OPSFIN_20260606_S50_doubled.SP3` | `f28a09f0420976ba…` | `20261007T215554Z-fit-S50e-op-0606/lin2-solve` | passed |
| `OPUS0OPSFIN_20260620_S50_doubled.SP3` | `a1cf61d9474a6452…` | `20261008T005002Z-fit-S50e-op-0620/lin4-solve` | passed |
| `OPUS0OPSFIN_20260623_S50_doubled.SP3` | `bd3e7c6b79aaa8fa…` | `20261008T171242Z-fit-S50e-op-0623/lin2-solve` | passed |
| `OPUS0OPSFIN_20260706_S50_doubled.SP3` | `7bf7d6036a0882d9…` | `20261008T194751Z-fit-S50e-op-0706/lin2-solve` | passed |
| `OPUS0OPSFIN_20260723_S50_doubled.SP3` | `a751654f712b07e3…` | `20261008T222335Z-fit-S50e-op-0723/lin2-solve` | passed |

