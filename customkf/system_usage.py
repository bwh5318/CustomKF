"""Read-only Windows machine CPU/RAM/GPU telemetry for the opt-in usage75 guard.

GPU: sum process counters per physical engine, then use the busiest engine.
https://learn.microsoft.com/windows/win32/api/pdh/nf-pdh-pdhgetformattedcounterarrayw
https://devblogs.microsoft.com/directx/gpus-in-the-task-manager/
Unavailable telemetry raises; it is never interpreted as zero utilization.
"""
from collections import defaultdict
import ctypes as C
from ctypes import wintypes as W
import math
import re
import time
import psutil


class Value(C.Structure):
    _fields_ = [('status', W.DWORD), ('value', C.c_double)]


class Item(C.Structure):
    _fields_ = [('name', W.LPWSTR), ('formatted', Value)]


def aggregate_gpu(items):
    engines = defaultdict(float)
    for name, status, value in items:
        if status not in (0, 1):
            continue  # Instances can disappear/create between collections.
        match = re.search(r'luid_(0x[0-9a-f]+_0x[0-9a-f]+)_phys_(\d+)_eng_(\d+)_engtype_', name, re.I)
        if not match or not math.isfinite(value) or value < 0:
            raise RuntimeError('Invalid GPU engine telemetry')
        engines[match.groups()] += value
    if not engines:
        raise RuntimeError('GPU engine telemetry unavailable')
    return min(100., max(engines.values()))


class UsageMonitor:
    def __init__(self):
        self.pdh = C.WinDLL('pdh')
        self.query, self.counter = W.HANDLE(), W.HANDLE()
        def bind(name, args):
            fn = getattr(self.pdh, name); fn.argtypes = args; fn.restype = W.DWORD
            return fn
        self.open = bind('PdhOpenQueryW', [W.LPCWSTR, C.c_size_t, C.POINTER(W.HANDLE)])
        self.add = bind('PdhAddEnglishCounterW', [W.HANDLE, W.LPCWSTR, C.c_size_t, C.POINTER(W.HANDLE)])
        self.collect = bind('PdhCollectQueryData', [W.HANDLE])
        self.array = bind('PdhGetFormattedCounterArrayW', [W.HANDLE, W.DWORD, C.POINTER(W.DWORD), C.POINTER(W.DWORD), C.c_void_p])
        self.close_query = bind('PdhCloseQuery', [W.HANDLE])
        try:
            self.check(self.open(None, 0, C.byref(self.query)))
            self.check(self.add(self.query, r'\GPU Engine(*)\Utilization Percentage', 0, C.byref(self.counter)))
            self.check(self.collect(self.query))
            psutil.cpu_percent(None)
            time.sleep(.5)  # Rate counters require two observations.
        except BaseException:
            self.close(); raise

    @staticmethod
    def check(status):
        if status != 0:
            raise OSError(f'Windows GPU telemetry failed: 0x{status:08x}')

    def sample(self):
        self.check(self.collect(self.query))
        for _ in range(3):
            size, count = W.DWORD(), W.DWORD()
            status = self.array(self.counter, 0x200, C.byref(size), C.byref(count), None)
            if status != 0x800007D2 or not size.value:
                raise RuntimeError(f'GPU telemetry sizing failed: 0x{status:08x}')
            buffer = C.create_string_buffer(size.value)
            status = self.array(self.counter, 0x200, C.byref(size), C.byref(count), buffer)
            if status == 0x800007D2:
                continue
            self.check(status)
            items = C.cast(buffer, C.POINTER(Item))
            gpu = aggregate_gpu([(items[i].name, items[i].formatted.status, items[i].formatted.value) for i in range(count.value)])
            memory = psutil.virtual_memory()
            return dict(cpu_percent=psutil.cpu_percent(None), gpu_percent=gpu,
                        ram_percent=100*(1-memory.available/memory.total), available_bytes=memory.available,
                        total_bytes=memory.total)
        raise RuntimeError('GPU counter instances changed repeatedly')

    def close(self):
        if self.query.value:
            self.close_query(self.query); self.query = W.HANDLE()


# Memory is governed by the guards' available-memory reserve, not by this percentage ceiling (user decision,
# 2 Oct 2026: start needs the job cap + 2 GiB free; a running job is asked to stop below 2 GiB and terminated below
# 1 GiB). RAM is still validated and recorded. CPU and GPU keep the 75% ceiling.
CEILING_KEYS = ('cpu_percent', 'gpu_percent')


def usage_reason(sample, ceiling=75.):
    for key in ('cpu_percent', 'gpu_percent', 'ram_percent'):
        value = sample[key]
        if not math.isfinite(value) or not 0 <= value <= 100:
            raise RuntimeError('Invalid machine utilization: '+key)
        if key in CEILING_KEYS and value >= ceiling:
            return key.replace('_percent', '_usage_limit')
    return None
