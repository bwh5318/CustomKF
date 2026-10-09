"""Guard controller tests: mocked pressure, tiny real job trees, no stress load."""
import json
import time
import unittest
from unittest.mock import patch
import psutil
from customkf.guard import run, Limits
from customkf.system_usage import UsageMonitor, aggregate_gpu, usage_reason

GOOD=dict(cpu_percent=10.,gpu_percent=5.,ram_percent=40.,available_bytes=20*2**30,total_bytes=32*2**30)

class UsageGuardTests(unittest.TestCase):
    def test_engine_aggregation(self):
        prefix='pid_1_luid_0x00000000_0x0001070f_phys_0_eng_'
        self.assertEqual(aggregate_gpu([(prefix+'0_engtype_3D',0,40),(prefix.replace('pid_1','pid_2')+'0_engtype_3D',1,36),(prefix+'1_engtype_Copy',0,20)]),76)
        with self.assertRaises(RuntimeError):aggregate_gpu([])

    def test_threshold_is_inclusive_and_validated(self):
        self.assertIsNone(usage_reason(GOOD))
        for key in ('cpu_percent','gpu_percent'):
            self.assertEqual(usage_reason(GOOD|{key:75}),key.replace('_percent','_usage_limit'))
        # RAM is validated but governed by the guards' memory reserve, not the ceiling (user decision 2 Oct 2026).
        self.assertIsNone(usage_reason(GOOD|{'ram_percent':95}))
        for key in ('cpu_percent','gpu_percent','ram_percent'):
            with self.assertRaises(RuntimeError):usage_reason(GOOD|{key:float('nan')})

    def test_real_profile_environment_and_telemetry(self):
        r,p=run(['tests.guard_probe','busy','1'],Limits(memory_mib=128,threads=2,cpu_percent=15,timeout_s=10),usage_ceiling=75)
        self.assertEqual(r['status'],'ok',r)
        self.assertEqual(len(r['cpu_affinity']),2)
        self.assertEqual(r['cpu_rate_readback'],1500)
        self.assertGreaterEqual(r['system_usage']['samples'],2)

    def test_preflight_refuses_pressure(self):
        with patch('customkf.system_usage.UsageMonitor') as monitor, patch('customkf.guard.Worker') as worker:
            monitor.return_value.sample.return_value=GOOD|dict(gpu_percent=75)
            r,_=run(['tests.guard_probe','normal'],Limits(memory_mib=128),usage_ceiling=75)
            self.assertEqual(r['status'],'setup_failed');worker.assert_not_called()

    def test_live_usage_breach_kills_job_tree(self):
        for key in ('cpu_percent','gpu_percent'):
            with self.subTest(key=key),patch('customkf.system_usage.UsageMonitor') as monitor:
                monitor.return_value.sample.side_effect=[GOOD,GOOD|{key:75}]
                r,p=run(['tests.guard_probe','descendant'],Limits(memory_mib=128,timeout_s=5),usage_ceiling=75)
                self.assertEqual(r['status'],key.replace('_percent','_usage_limit'),r)
                child=json.loads((p/'child.json').read_text())['pid']
                for _ in range(20):
                    if not psutil.pid_exists(child):break
                    time.sleep(.05)
                self.assertFalse(psutil.pid_exists(child));self.assertTrue((p/'STOP.json').exists())

    def test_telemetry_failure_fails_closed(self):
        with patch('customkf.system_usage.UsageMonitor') as monitor:
            monitor.return_value.sample.side_effect=[GOOD,OSError('GPU counters lost')]
            r,p=run(['tests.guard_probe','descendant'],Limits(memory_mib=128,timeout_s=5),usage_ceiling=75)
            self.assertEqual(r['status'],'controller_failed')
            child=json.loads((p/'child.json').read_text())['pid']
            for _ in range(20):
                if not psutil.pid_exists(child):break
                time.sleep(.05)
            self.assertFalse(psutil.pid_exists(child))

if __name__=='__main__':unittest.main()
