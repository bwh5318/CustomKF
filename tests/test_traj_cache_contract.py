"""Trajectory-cache contract (review finding M10): tiny synthetic caches, no integration, no guard needed.

    C:\\anaconda\\python.exe -m unittest tests.test_traj_cache_contract -v

Each case writes a cache the way `claude.roadmap.traj_cache integrate` does (same arrays, same metadata
helpers) and loads it through `cached_products` with a minimal stand-in pilot.
"""
import json
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
import numpy as np
from customkf.prepare_stage2 import sha
from customkf.propagation import IntegrationSettings
from customkf.dynamic_observation import SETTINGS
from claude.roadmap.traj_cache import cached_products, contract, initial_and_parameters, integration, key, trajectory_grid

FIXTURE, CONFIG = "f"*64, "c"*64
ORIGIN = 1469750390000000000


class Model:
    parameter_names = ("D0", "Y0", "B0", "Bc1", "Bs1")
    parameter_scales = np.full(5, 1e-7)


class OtherModel(Model):
    parameter_names = Model.parameter_names+("Dc2", "Ds2")


def pilot(duration=20., sats=("G01", "G02"), identity=True, model=Model):
    context = dict(origin_ns=ORIGIN, model=model(), epoch=None, records={}, navigation_cutoff_ns=ORIGIN)
    if identity:
        context.update(fixture_sha256=FIXTURE, config_sha256=CONFIG)
    sats = sorted(sats)
    return SimpleNamespace(context=context, duration=duration, sats=sats, estimate=(),
                           seeds={s: np.arange(6.)*1e6+i for i, s in enumerate(sats)},
                           index={f"orbit:{s}:0": 6*i for i, s in enumerate(sats)}, nominal={s: -1e-7 for s in sats})


def write(folder, p, x, *, sats=None, times=None, legacy=False, settings=SETTINGS, **override):
    """One group's cache as traj_cache.main writes it; `legacy` omits the fields added for M10."""
    folder.mkdir(parents=True)
    times = trajectory_grid(p.duration) if times is None else times
    arrays, keys = dict(times=times), {}
    for sat in (p.sats if sats is None else sats):
        initial, q = initial_and_parameters(p, sat, x)
        ramp = times[:, None]
        arrays[f"{sat}_states"] = initial+ramp*1e-3
        arrays[f"{sat}_stm"] = np.eye(6)+ramp[:, :, None]*1e-6
        arrays[f"{sat}_sensitivity"] = np.ones((len(times), 6, 5))*ramp[:, :, None]
        keys[sat] = key(initial, q)
    np.savez_compressed(folder/"trajectories.npz", **arrays)
    meta = dict(status="trajectory_cache", satellites=list(keys), keys=keys, cache_sha256=sha(folder/"trajectories.npz"),
                fixture_sha256=FIXTURE, config_sha256=CONFIG)
    if not legacy:
        meta.update(contract(p, times, settings))
    meta.update(override)
    (folder/"trajectories.json").write_text(json.dumps(meta, indent=2))
    return folder/"trajectories.npz"


class TrajectoryCacheContract(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="traj_cache_contract_"))
        self.p = pilot()
        self.x = np.zeros(12)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def refused(self, files, pattern, p=None, **kwargs):
        with self.assertRaisesRegex(ValueError, pattern):
            cached_products(self.p if p is None else p, self.x, files, **kwargs)

    def test_matching_cache_accepted_and_evaluates_over_the_arc(self):
        files = [write(self.root/"g0", self.p, self.x, sats=["G01"]), write(self.root/"g1", self.p, self.x, sats=["G02"])]
        products = cached_products(self.p, self.x, files)
        self.assertEqual(sorted(products.trajectories), self.p.sats)
        for t in (0., 7.5, 20.):
            self.assertTrue(np.isfinite(products.state("G02", t)).all())
        meta = json.loads((self.root/"g0"/"trajectories.json").read_text())
        self.assertEqual((meta["origin_ns"], meta["duration_s"], meta["grid"]["count"]), (ORIGIN, 20., 3))
        # The recorded fingerprint survives the JSON round trip and equals a fresh computation.
        self.assertEqual(meta["integration"], integration(SETTINGS, Model()))

    def test_legacy_cache_still_accepted(self):
        cached_products(self.p, self.x, [write(self.root/"g", self.p, self.x, legacy=True)])

    def test_caller_without_identity_is_not_identity_checked(self):
        cached_products(pilot(identity=False), self.x, [write(self.root/"g", self.p, self.x, fixture_sha256="0"*64)])

    def test_identity_from_keywords(self):
        bare = pilot(identity=False)
        files = [write(self.root/"g", self.p, self.x)]
        cached_products(bare, self.x, files, fixture_sha256=FIXTURE, config_sha256=CONFIG)
        self.refused(files, "fixture_sha256", p=bare, fixture_sha256="0"*64)
        self.refused(files, "fixture_sha256", fixture_sha256="0"*64)   # keyword overrides the context

    def test_wrong_fixture_refused(self):
        self.refused([write(self.root/"g", self.p, self.x, fixture_sha256="0"*64)], "fixture_sha256")

    def test_wrong_config_refused(self):
        self.refused([write(self.root/"g", self.p, self.x, legacy=True, config_sha256="0"*64)], "config_sha256")

    def test_unrecorded_identity_refused_when_caller_has_one(self):
        path = write(self.root/"g", self.p, self.x)
        meta = json.loads((path.parent/"trajectories.json").read_text())
        del meta["fixture_sha256"]
        (path.parent/"trajectories.json").write_text(json.dumps(meta))
        self.refused([path], "fixture_sha256 None")

    def test_wrong_origin_refused(self):
        self.refused([write(self.root/"g", self.p, self.x, origin_ns=ORIGIN+86400*10**9)], "origin")

    def test_wrong_duration_refused(self):
        self.refused([write(self.root/"g", self.p, self.x, duration_s=40.)], "origin")

    def test_insufficient_coverage_refused_even_for_legacy_metadata(self):
        self.refused([write(self.root/"g", self.p, self.x, legacy=True, times=np.array([0., 1.]))], "covers")

    def test_grid_other_than_the_integration_grid_refused(self):
        self.refused([write(self.root/"g", self.p, self.x, legacy=True, times=np.array([0., 5., 20.]))], "grid")
        self.refused([write(self.root/"h", self.p, self.x, legacy=True, times=trajectory_grid(40.))], "grid")

    def test_wrong_settings_fingerprint_refused(self):
        files = [write(self.root/"g", self.p, self.x, settings=IntegrationSettings())]
        self.refused(files, "settings")
        cached_products(self.p, self.x, files, settings=IntegrationSettings())
        self.refused([write(self.root/"h", self.p, self.x)], "settings", settings=IntegrationSettings(rtol=1e-11))

    def test_different_model_refused(self):
        self.refused([write(self.root/"g", self.p, self.x)], "settings or model", p=pilot(model=OtherModel))

    def test_corrupted_content_refused(self):
        path = write(self.root/"g", self.p, self.x)
        data = bytearray(path.read_bytes())
        data[len(data)//2] ^= 0xFF
        path.write_bytes(bytes(data))
        self.refused([path], "content hash")

    def test_missing_satellite_refused(self):
        self.refused([write(self.root/"g", self.p, self.x, sats=["G01"])], "incomplete")

    def test_foreign_satellite_refused(self):
        self.refused([write(self.root/"g", pilot(sats=("G01", "G02", "G03")), np.zeros(18))], "G03")

    def test_other_linearization_point_refused(self):
        self.refused([write(self.root/"g", self.p, self.x+1e-3)], "linearization point")

    def test_review_probe_now_refused(self):
        """Astra's M10 probe: valid keys and content hash, wrong fixture/config/origin, 1 s of a 20 s request."""
        files = [write(self.root/"g", self.p, self.x, times=np.array([0., 1.]), fixture_sha256="0"*64,
                       config_sha256="1"*64, origin_ns=ORIGIN+1)]
        self.refused(files, "")
        # Each defect is refused on its own, too (legacy metadata, bare caller: only the grid is checkable).
        self.refused([write(self.root/"h", self.p, self.x, legacy=True, times=np.array([0., 1.]))], "covers",
                     p=pilot(identity=False))


if __name__ == "__main__":
    unittest.main()
