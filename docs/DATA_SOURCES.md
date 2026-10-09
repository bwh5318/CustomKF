# Data sources and citations

Every external input the pipeline uses, where it comes from, and how it enters.
- **Most inputs** are downloaded by the project's own scripts, and their hashes are recorded in
  `Opus_Fork/datastore/index.json` (rebuilt with `Opus_Fork.store --rebuild`).
- **Large data files are not redistributed** in this repository (`.gitignore`). Fetch them from the sources below.
- **Fit inputs versus references.** Fit inputs feed the estimator. Reference products are read only by scoring code
  (`customkf/stage5_pilot.py:forbid_precise_product_reads` guards the fitting paths). Model choices were, however,
  selected using reference-scored outcomes; that is recorded separately as a selection effect.
- **Latency column.** A published analytical model existing in advance is not the same as the exact file version used
  here having existed at a cut-off. No version below was verified for a cut-off, and receipt times were not recorded
  (corrected 8 Oct 2026, documentation review F6).

## Fit inputs

| Input | Source | Fetched by | Latency for a rapid product |
|---|---|---|---|
| Station observations: daily 30 s RINEX 3 (`*_R_YYYYDDD0000_01D_30S_MO.crx.gz`) | IGS, through the BKG GNSS data centre `https://igs.bkg.bund.de/root_ftp/IGS/obs/` | `Opus_Fork.fetch station` | Normally hours after the day ends; receipt times not recorded |
| Broadcast navigation, merged multi-GNSS (`BRDC00WRD_R_..._MN.rnx.gz`), for the day and the previous day | IGS/BKG `.../IGS/BRDC/` | `Opus_Fork.fetch product --kind brdc` | The message is real time; the merged daily file's availability was not recorded |
| Earth orientation, daily (`finals2000A.all`) | IERS Rapid Service / USNO, `https://maia.usno.navy.mil/ser7/finals2000A.all` | `customkf.prepare_stage2` | **Retrospective as used.** The file holds final and rapid values downloaded after the dates. A rapid product would use the prediction part available at the cut-off. |
| Sub-daily EOP model (ORTHO_EOP, CNMTX) | IERS Conventions (2010), chapter 8 software, `https://iers-conventions.obspm.fr/conventions/content/chapter8/software/` | tracked in `Opus_Fork/datastore/static/iers_ch8/`; ported in `Opus_Fork/subdaily_eop.py` | A model, available in advance |
| Planetary ephemeris DE440s | JPL NAIF, `https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de440s.bsp` | `customkf.prepare_stage2` | Available in advance |
| Gravity field EGM2008 (degree/order 12 used) | ICGEM, GFZ Potsdam, `https://icgem.gfz.de/` | `customkf.prepare_stage2` | Available in advance |
| Antenna calibrations `igs20.atx` | IGS, `https://files.igs.org/pub/station/general/igs20.atx` | `customkf.prepare_stage3` | **Retrospective as used.** A dated, occasionally updated file; the version used was retrieved later |
| Station coordinates IGS20 (`IGc20.ssc`, `soln_IGc20.snx`, `psd_IGc20.snx`) | IGS, `https://files.igs.org/pub/station/coord/IGc20/` | `customkf.prepare_stage3` | **Retrospective as used.** A cumulative solution updated every few weeks; the version used was retrieved later |
| Ocean-tide loading `FES2014b.BLQ` | AIUB (Bernese user files), `https://download.aiub.unibe.ch/BSWUSER54/REF/FES2014b.BLQ`; computed with the Onsala loading service (Scherneck and Bos) | `customkf.prepare_stage3` | Available in advance |
| Satellite metadata SINEX (mass, transmit power, block) | IGS, `https://files.igs.org/pub/station/general/igs_satellite_metadata.snx` | tracked at `Opus_Fork/datastore/static/` (retrieved 22 Sep 2026) | **Retrospective as used** (a September file applied to June–August). Changes rarely |
| **Optional:** TU Wien GRAD operational site-wise gradients (`YYYYDDD.grad_g`) | VMF Data Server, TU Wien, `https://vmf.geo.tuwien.ac.at/trop_products/GNSS/GRAD/GRAD_OP/daily/` | `Opus_Fork/experiments/gradients/acquire_day.sh` | **Not rapid.** The last file an arc needs carried a server Last-Modified time about 40 h after the arc ended, read later. That is not an observed first availability or a verified issue time |
| **Optional, not adopted:** GPT3 empirical grid (`gpt3_1.grd`) | VMF Data Server, `https://vmf.geo.tuwien.ac.at/codes/` | `Opus_Fork/experiments/gradients/acquire.sh` | A model, available in advance |

## References (scoring only)

| Product | Source | Use |
|---|---|---|
| IGS final orbits (`IGS0OPSFIN_YYYYDDD0000_01D_15M_ORB.SP3`) | IGS combined final, through BKG `.../IGS/products/<week>/` | The reference for the modern full-day scores (from 20 Sep 2026). **A reference, not truth.** |
| NGA precise ephemeris (`nga<week><dow>.sp3`, centre of mass) | National Geospatial-Intelligence Agency GNSS products, `https://earth-info.nga.mil/index.php?action=gnss&dir=gnss` | The bar: the project's objective is to be closer to IGS final than NGA PE is |
| IGS rapid orbits | IGS through BKG | Early development comparisons only (some first-phase 3D figures) |

## Software and models adapted from others

| Item | Use | Licence and notes |
|---|---|---|
| RNXCMP 4.2.0 (`CRX2RNX`), Y. Hatanaka, GSI | Decompressing Hatanaka RINEX | Vendored with its licence in `vendor/rnxcmp-4.2.0/` |
| ERFA (via PyERFA), derived from IAU SOFA | Precession-nutation, Earth rotation angle | BSD-style ERFA licence |
| IERS Conventions software (ORTHO_EOP, CNMTX, DEHANTTIDEINEL) | Sub-daily EOP; station tide screen | Python ports in `Opus_Fork/subdaily_eop.py` and `Opus_Fork/station_tides.py`. These are **not IERS software**; the IERS licence asks derived works to say so and to describe their differences. The original Fortran is tracked with its notice |
| RTKLIB (T. Takasu), `rtkcmn.c`, `ppp.c` | Reference for the initial NMF mapping and reduced tide formulations in `customkf/station_models.py` | BSD 2-clause; see `THIRD_PARTY_NOTICES.md` |

## Suggested citations

- **IGS products and data:** Johnston, G., Riddell, A., Hausler, G. (2017). The International GNSS Service. In
  *Springer Handbook of Global Navigation Satellite Systems*, 967–982. doi:10.1007/978-3-319-42928-1_33.
- **IGS20 / igs20.atx:** see the IGS station coordinate and antenna pages at `https://files.igs.org/pub/station/`.
- **IERS Conventions:** Petit, G., Luzum, B. (eds.) (2010). *IERS Conventions (2010)*. IERS Technical Note 36.
- **DE440:** Park, R. S., et al. (2021). The JPL Planetary and Lunar Ephemerides DE440 and DE441. *The Astronomical
  Journal* 161, 105. doi:10.3847/1538-3881/abd414.
- **EGM2008:** Pavlis, N. K., et al. (2012). The development and evaluation of the Earth Gravitational Model 2008.
  *JGR Solid Earth* 117, B04406. doi:10.1029/2011JB008916.
- **ECOM:** Arnold, D., et al. (2015). CODE's new solar radiation pressure model for GNSS orbit determination.
  *Journal of Geodesy* 89, 775–791. doi:10.1007/s00190-015-0814-4.
- **GRAD and GPT3:** Landskron, D., Böhm, J. (2018). VMF3/GPT3: refined discrete and empirical troposphere mapping
  functions. *Journal of Geodesy* 92, 349–360. doi:10.1007/s00190-017-1066-2. Also Landskron, D., Böhm, J. (2018). Refined discrete and empirical
  horizontal gradients in VLBI analysis. *Journal of Geodesy* 92, 1387–1399. doi:10.1007/s00190-018-1127-1.
- **Hatanaka compression:** Hatanaka, Y. (2008). A Compression Format and Tools for GNSS Observation Data. *Bulletin
  of the Geographical Survey Institute* 55, 21–30.
- **FES2014:** Lyard, F., et al. (2021). FES2014 global ocean tide atlas. *Ocean Science* 17, 615–649.
  doi:10.5194/os-17-615-2021.
- **GPS-IIIA effective mass (2,600 kg):** Steigenberger, P., Thoelert, S., Montenbruck, O. (2020). GPS III Vespucci:
  results of half a year in orbit. *Advances in Space Research* 66, 2773–2785. doi:10.1016/j.asr.2020.03.026.
- **ERFA / SOFA:** ERFA (Essential Routines for Fundamental Astronomy), `https://github.com/liberfa/erfa`, derived
  from the IAU SOFA library (`https://www.iausofa.org/`). Production uses `xys06a` (angles-based CIP); the oracle's
  default uses `xy06` (series); ERFA documents microarcsecond differences between them.
