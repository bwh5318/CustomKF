# Third-party notices

The project's own code is under the MIT licence (`LICENSE`). The components and adaptations below keep their
original terms.

The initial NMF and reduced tide formulations in customkf/station_models.py were adapted with reference to RTKLIB rtkcmn.c and ppp.c. Copyright (C) 2007-2018 by T. Takasu. The original package license follows. The estimator is our own implementation.

The RTKLIB software package is distributed under the following BSD 2-clause
license (http://opensource.org/licenses/BSD-2-Clause) and additional two
exclusive clauses. Users are permitted to develop, produce or sell their own
non-commercial or commercial products utilizing, linking or including RTKLIB as
long as they comply with the license.

          Copyright (c) 2007-2013, T. Takasu, All rights reserved.

Redistribution and use in source and binary forms, with or without modification,
are permitted provided that the following conditions are met:

- Redistributions of source code must retain the above copyright notice, this
  list of conditions and the following disclaimer.

- Redistributions in binary form must reproduce the above copyright notice, this
  list of conditions and the following disclaimer in the documentation and/or
  other materials provided with the distribution.

- The software package includes some companion executive binaries or shared
  libraries necessary to execute APs on Windows. These licenses succeed to the
  original ones of these software. 

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE
GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF
THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

The project-local CRX2RNX decoder is GSI RNXCMP 4.2.0. Its license and provenance are retained in vendor/rnxcmp-4.2.0/. Cite Hatanaka (2008), A Compression Format and Tools for GNSS Observation Data, Bulletin of the Geographical Survey Institute 55, 21-30.

## IERS Conventions software

`Opus_Fork/datastore/static/iers_ch7/*.F` and `iers_ch8/*.F` are original IERS Conventions (2010) routines,
distributed here unmodified with the IERS Conventions Software License notice intact in each file (Copyright (C)
2008 IERS Conventions Center). The following Python modules are derived works. They are **not IERS software**, and
they are neither distributed by nor endorsed by the IERS Conventions Center. Each module's header describes how it is
based on and differs from the original, and its routines are renamed:
- `Opus_Fork/subdaily_eop.py`: ORTHO_EOP.F and CNMTX.F (sub-daily ocean-tidal polar motion and UT1);
- `Opus_Fork/station_tides.py`: DEHANTTIDEINEL.F with ST1IDIU, ST1ISEM, ST1L1, STEP2DIU and STEP2LON;
- `validation/oracle/frame.py` (`ocean_tidal_eop`): an independent re-implementation of ORTHO_EOP.F, reading the
  CNMTX.F and ORTHO_EOP.F tables from the original files at run time.

As the licence asks, results obtained with these routines acknowledge the IERS Conventions software: Petit, G.,
Luzum, B. (eds.) (2010), IERS Conventions (2010), IERS Technical Note 36.

## ERFA and SOFA

Precession-nutation, Earth rotation and time-scale functions come from ERFA (Essential Routines for Fundamental
Astronomy) through the PyERFA package, a dependency installed separately and not vendored here. ERFA is derived from
the IAU SOFA library and is distributed under a BSD-style licence; it is not SOFA software. See
`https://github.com/liberfa/erfa` and `https://www.iausofa.org/`.

## Tracked data files

- `Opus_Fork/datastore/static/igs_satellite_metadata.snx`: IGS satellite metadata (International GNSS Service, open
  data; cite the IGS as in `docs/DATA_SOURCES.md`).
- JPL Horizons check vectors used by tests: JPL Solar System Dynamics, Horizons system.
- Large inputs (observations, navigation, reference orbits, EOP, ephemerides, gravity, ocean loading, the Desai and
  Sibois coefficient table) are not distributed in the public release; see `docs/DATA_SOURCES.md` and `SETUP.md`.
