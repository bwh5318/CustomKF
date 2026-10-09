"""Characterization of the Opus_Fork guard's GPU hold and profile limits (review findings M13, N06).

    C:\\anaconda\\python.exe -m unittest tests.test_guard_hold_semantics -v

Pure `usage_check` simulations on synthetic 0.5 s sample series (the guard's sampling interval); no job, no
telemetry, no guard needed. These tests pin the CURRENT behaviour, including its documented limitation, so that a
policy change shows up as a failing test rather than silently. They do not change or endorse the policy: a strict
utilization ceiling would be a user-authorized policy change (Phase 3 step 6), not a fix.
"""
import unittest

from Opus_Fork import guard
from Opus_Fork.guard import GPU_SUSTAIN_S, PROFILES, Limits, usage_check

GOOD = dict(cpu_percent=10., gpu_percent=5., ram_percent=40., available_bytes=20*2**30, total_bytes=32*2**30)
HIGH = dict(GOOD, gpu_percent=80.)
GAP = dict(GOOD, gpu_percent=None, gpu_error="OSError: 0xc0000bba")
DT = 0.5


def simulate(series):
    """Feed samples every DT s as the running-job loop does. Returns (index of the stop or None, reason)."""
    since = None
    for i, sample in enumerate(series):
        try:
            reason, since = usage_check(sample, 75, since, i*DT)
        except RuntimeError as error:
            return i, str(error)
        if reason:
            return i, reason
    return None, None


class GpuHold(unittest.TestCase):
    def test_continuous_high_gpu_stops_after_the_hold(self):
        stop, reason = simulate([HIGH]*100)
        self.assertEqual(reason, "gpu_usage_limit")
        self.assertAlmostEqual(stop*DT, GPU_SUSTAIN_S)

    def test_intermittent_high_gpu_never_stops(self):
        """M13's synthetic case: 80% GPU with one low reading before each hold completes (95% of samples high)."""
        period = int(GPU_SUSTAIN_S/DT)                  # one low sample every 10 s
        series = [GOOD if i % period == period-1 else HIGH for i in range(int(40/DT))]
        high = sum(s is HIGH for s in series)/len(series)
        self.assertGreaterEqual(high, 0.95)
        self.assertEqual(simulate(series), (None, None))   # documented limitation, not a ceiling

    def test_intermittent_telemetry_gaps_never_fail(self):
        period = int(GPU_SUSTAIN_S/DT)
        series = [GOOD if i % period == period-1 else GAP for i in range(int(40/DT))]
        self.assertEqual(simulate(series), (None, None))

    def test_lasting_telemetry_loss_fails_closed_after_the_hold(self):
        stop, reason = simulate([GAP]*100)
        self.assertIn("telemetry unavailable", reason)
        self.assertAlmostEqual(stop*DT, GPU_SUSTAIN_S)

    def test_short_job_can_finish_inside_the_hold(self):
        self.assertEqual(simulate([HIGH]*int(GPU_SUSTAIN_S/DT)), (None, None))

    def test_cpu_stops_on_one_reading_even_inside_a_gpu_streak(self):
        series = [HIGH]*5+[dict(HIGH, cpu_percent=75.)]
        self.assertEqual(simulate(series), (5, "cpu_usage_limit"))
        # RAM no longer stops through the ceiling; the memory reserve governs it (user decision 2 Oct 2026).
        self.assertEqual(simulate([HIGH]*5+[dict(HIGH, ram_percent=95.)]), simulate([HIGH]*6))


class ProfileLimits(unittest.TestCase):
    """N06: profile defaults are narrower than what Limits.validate accepts; the validator is not an authorization."""

    def test_fork8_is_one_thread_eight_processes(self):
        self.assertEqual(PROFILES["fork8"], (4096, 50, 1, 8, 512))
        self.assertEqual(PROFILES["fork8t"], (4096, 50, 8, 8, 512))
        self.assertEqual(PROFILES["usage75"], (4096, 15, 2, 4, 128))

    def test_every_profile_validates(self):
        for memory, cpu, threads, processes, scratch in PROFILES.values():
            Limits(memory_mib=memory, cpu_percent=cpu, threads=threads, processes=processes, scratch_mib=scratch).validate()

    def test_validator_range_is_wider_than_any_profile(self):
        """Pinned so a Phase 3 policy encoding (named maxima) visibly changes it."""
        Limits(memory_mib=6144, cpu_percent=60, threads=12, processes=12).validate()
        for bad in (dict(memory_mib=6145), dict(cpu_percent=60.1), dict(threads=13), dict(processes=13)):
            with self.assertRaises(ValueError):
                Limits(**bad).validate()

    def test_reserves_cannot_go_below_the_policy(self):
        """Floors since the user's 2 Oct 2026 decision: reserve 2 GiB, emergency 1 GiB, emergency < reserve."""
        Limits().validate()
        for bad in (dict(reserve_gib=1.9), dict(emergency_gib=.9), dict(emergency_gib=2)):
            with self.assertRaises(ValueError):
                Limits(**bad).validate()


if __name__ == "__main__":
    unittest.main()
