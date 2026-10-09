"""The bar: how close is NGA precise ephemeris to the IGS final orbit, on OUR day?

    python -m customkf.guard --profile usage75 --timeout 300 -- opusfork.baseline

The project objective is "closer to IGS final than NGA PE is". Until now the project
scored against IGS *rapid* and compared with a stored 359-day NGA average (10.13 cm
3D / 3.62 cm URE, COMPARISON_CONTRACT.md). This worker measures the three quantities
that actually decide the objective, all on 2026-08-02, from files already pinned on
disk, with no fitting of any kind:

  1. NGA PE    vs IGS final - the bar to beat.
  2. IGS rapid vs IGS final - how far the reference we have been scoring against sits
                              from the reference the objective names.
  3. Our best station fit (25 stations, 24 h, ECOM5) vs IGS final - where we stand.

Frames are not relabelled or fitted. NGA is WGS84(G2296), IGS is IGc20, and both
declare satellite centre of mass. The raw difference is the primary number; a
separate 7-parameter Helmert residual says how much a datum change could absorb.
"""
import argparse
import json
import os
from pathlib import Path
import numpy as np

from customkf.frames import EarthOrientation, FrameEpoch
from customkf.prepare_stage2 import sha
from customkf.sp3 import epoch_tag

from .blocks import satellite_blocks, group
from .paths import ROOT, STAGE0, STAGE2, STAGE3, RESULTS
from .score import Declared, Product, helmert_residual, pooled, rac

DAY = "2026-08-02"
MIDNIGHT = epoch_tag("* 2026 08 02 00 00 00")
BEST_SOLUTION = ROOT/"claude/runs/20260913T220409Z-long-NL-25st-24h/lin2-solve/solution.npz"
BEST_FIXTURE = ROOT/"claude/runs/20260913T214809Z-roadmap-stations/prepare-25-24h/fixture.json"


class Fit:
    """One of our own solutions read back as a product, on its saved state grid.

    States are stored in inertial (GCRS) axes relative to the fixture origin. GCRS
    axes do not depend on which epoch is called the origin, so positions compare
    directly with a reference built on a different origin as long as the key stays
    the absolute GPS nanosecond. No velocity is needed: the reference always supplies
    the R/A/C axes.
    """

    def __init__(self, npz_path, fixture_path, eop):
        # Read each npz member exactly once. NpzFile.__getitem__ decompresses the whole array
        # on every access, so indexing `f["states"][si, ti]` inside the loop below re-read a
        # 27x287x6 array 7749 times and cost gigabytes; the streaming restore carries the
        # same warning (claude/roadmap/streaming.py:Accumulator.restore).
        with np.load(npz_path) as f:
            satellites = [str(s) for s in f["satellites"]]
            times = [float(t) for t in f["times_s"]]
            states = np.array(f["states"][:, :, :3], dtype=float)
        self.origin_ns = int(json.loads(Path(fixture_path).read_text())["context"]["origin_ns"])
        self.epoch = FrameEpoch(self.origin_ns, eop)
        self.declared = Declared("our fit: 25 stations, 24 h, ECOM5", "IGc20", "COM")
        self.states = {}
        for si, sat in enumerate(satellites):
            for ti, t in enumerate(times):
                self.states[sat, self.origin_ns+int(round(t*1e9))] = states[si, ti]
        self._rotations = {}

    def keys(self):
        return set(self.states)

    def position(self, sat, t):
        return self.states[sat, self.origin_ns+int(round(t*1e9))]

    def rotation(self, t):
        if t not in self._rotations:
            self._rotations[t] = self.epoch.celestial_to_terrestrial(t)
        return self._rotations[t]


class OnOrigin:
    """Present `inner` on another origin's elapsed-second convention.

    Everything is keyed by absolute GPS nanoseconds; this only translates the
    elapsed second a caller passes, so one reference can score candidates whose
    fixtures used different origins.
    """

    def __init__(self, inner, origin_ns):
        self.inner, self.origin_ns = inner, int(origin_ns)
        self.declared = inner.declared

    def _inner_t(self, t):
        return (self.origin_ns+int(round(t*1e9))-self.inner.origin_ns)/1e9

    def keys(self):
        return self.inner.keys()

    def position(self, sat, t):
        return self.inner.position(sat, self._inner_t(t))

    def velocity(self, sat, t):
        return self.inner.velocity(sat, self._inner_t(t))

    def rotation(self, t):
        return self.inner.rotation(self._inner_t(t))


def compare(reference, candidate, blocks, label):
    """Raw contract score, per satellite and block, plus the Helmert diagnostic."""
    keys = sorted(reference.keys() & candidate.keys())
    if not keys:
        raise ValueError("No common satellite-epochs: "+label)
    table = {(sat, ns): rac(reference, candidate, sat, (ns-reference.origin_ns)/1e9) for sat, ns in keys}
    sats = sorted({s for s, _ in table})
    raw = pooled(list(table.values()))
    result = dict(
        label=label, candidate=candidate.declared.label, reference=reference.declared.label,
        candidate_frame=candidate.declared.frame, reference_frame=reference.declared.frame,
        frames_identical=candidate.declared.frame == reference.declared.frame,
        satellites=len(sats), raw=raw,
        per_satellite={s: pooled([v for (a, _), v in table.items() if a == s]) | {"block": blocks.get(s)}
                       for s in sats},
        by_block={g: pooled([v for (a, _), v in table.items() if blocks.get(a) == g])
                  for g in sorted({blocks[s] for s in sats if s in blocks})})
    residual, parameters = helmert_residual(reference, candidate, set(table))
    left = pooled(list(residual.values()))
    translations = np.array([p["translation_m"] for p in parameters.values()])
    scales = np.array([p["scale"] for p in parameters.values()])
    result["helmert_diagnostic"] = dict(
        note="DIAGNOSTIC ONLY: per-epoch 7-parameter similarity fit; never replaces the raw score",
        epochs=len(parameters), residual=left,
        squared_error_absorbed_percent=float(100*(1-left["rms_3d_m"]**2/raw["rms_3d_m"]**2)),
        mean_translation_mm=(translations.mean(axis=0)*1000).tolist(),
        std_translation_mm=(translations.std(axis=0)*1000).tolist(),
        mean_scale_ppb=float(scales.mean()*1e9), std_scale_ppb=float(scales.std()*1e9))
    return result


def main():
    if not os.environ.get("CUSTOMKF_RUN_DIR"):
        raise RuntimeError("Use customkf.guard")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-fit", action="store_true", help="score the reference products only")
    args = parser.parse_args()
    out = Path(os.environ["CUSTOMKF_RUN_DIR"])
    eop = EarthOrientation(STAGE2/"finals2000A.all")
    blocks = {s: group(t) for s, (t, _) in satellite_blocks(DAY).items()}

    declared = {
        "igs_final": (STAGE0/"IGS0OPSFIN_20262140000_01D_15M_ORB.SP3",
                      Declared("IGS final (IGS0OPSFIN day 214)", "IGc20", "COM")),
        "nga_pe": (STAGE0/"nga24300.sp3",
                   Declared("NGA PE (nga24300 day 214)", "WGS84", "COM", legacy_a_time_system="GPS")),
        "igs_rapid": (STAGE3/"IGS0OPSRAP_20262140000_01D_15M_ORB.SP3.gz",
                      Declared("IGS rapid (IGS0OPSRAP day 214)", "IGc20", "COM")),
    }
    products, provenance = {}, {}
    for name, (path, decl) in declared.items():
        products[name] = Product(path, decl, MIDNIGHT, eop)
        provenance[name] = dict(path=path.relative_to(ROOT).as_posix(), sha256=sha(path),
                                frame=decl.frame, declared_origin=decl.origin, label=decl.label,
                                sp3_version=products[name].raw.version,
                                comments=products[name].raw.comments,
                                valid_samples=len(products[name].keys()))
    reference = products["igs_final"]

    report = dict(status="reference_baseline_measurement_not_accuracy_acceptance", day=DAY,
                  note="Raw unaligned contract scores. NGA is WGS84(G2296) and IGS is IGc20: the "
                       "frame labels differ and are neither relabelled nor fitted away.",
                  provenance=provenance, comparisons={})
    report["comparisons"]["nga_vs_igs_final"] = compare(
        reference, products["nga_pe"], blocks, "NGA PE vs IGS final")
    report["comparisons"]["igs_rapid_vs_igs_final"] = compare(
        reference, products["igs_rapid"], blocks, "IGS rapid vs IGS final")

    if not args.skip_fit and BEST_SOLUTION.exists():
        fit = OnOrigin(Fit(BEST_SOLUTION, BEST_FIXTURE, eop), MIDNIGHT)
        provenance["our_fit"] = dict(path=BEST_SOLUTION.relative_to(ROOT).as_posix(),
                                     sha256=sha(BEST_SOLUTION), fixture_sha256=sha(BEST_FIXTURE),
                                     label=fit.declared.label,
                                     frame="IGc20 through fixed station coordinates",
                                     valid_samples=len(fit.keys()))
        report["comparisons"]["our_fit_vs_igs_final"] = compare(
            reference, fit, blocks, "our 25-station 24 h ECOM5 fit vs IGS final")
        report["comparisons"]["our_fit_vs_igs_rapid"] = compare(
            products["igs_rapid"], fit, blocks, "our fit vs IGS rapid (should reproduce 0.1464 m)")

    text = json.dumps(report, indent=2, default=float)+"\n"
    (out/"baseline.json").write_text(text)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS/"baseline_nga_vs_igs_final.json").write_text(text)
    for name, c in report["comparisons"].items():
        r = c["raw"]
        rac_cm = "/".join(f"{v*100:.2f}" for v in r["rms_rac_m"])
        print(f"{name:26s} sats={c['satellites']:3d} n={r['samples']:5d}  "
              f"3D={r['rms_3d_m']*100:8.3f} cm  URE={r['rms_orbit_ure_m']*100:7.3f} cm  "
              f"R/A/C={rac_cm} cm  helmert-left={c['helmert_diagnostic']['residual']['rms_3d_m']*100:7.3f} cm")
    print("\nWrote "+str(out/"baseline.json"))


if __name__ == "__main__":
    main()
