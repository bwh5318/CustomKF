"""Tiny controlled workers; never allocate more than 256 MiB virtual commit."""
import ctypes as C
import json
import os
from pathlib import Path
import subprocess
import sys
import time

mode = sys.argv[1]
folder = Path(os.environ["CUSTOMKF_RUN_DIR"])
if mode == "normal":
    import psutil
    print(json.dumps({"affinity": psutil.Process().cpu_affinity(),
                      "threads_env": os.environ["MKL_NUM_THREADS"]}), flush=True)
elif mode == "allocation":
    import psutil
    kernel = C.WinDLL("kernel32", use_last_error=True)
    alloc = kernel.VirtualAlloc
    alloc.argtypes, alloc.restype = [C.c_void_p, C.c_size_t, C.c_ulong, C.c_ulong], C.c_void_p
    before = psutil.Process().memory_info().private
    block = alloc(None, 256*2**20, 0x3000, 0x04)
    error = C.get_last_error()
    if block:
        free = kernel.VirtualFree
        free.argtypes = [C.c_void_p, C.c_size_t, C.c_ulong]
        free(block, 0, 0x8000)
    after = psutil.Process().memory_info().private
    print(json.dumps({"allocation_denied": not bool(block), "winerror": error,
                      "private_before":before, "private_after":after}), flush=True)
    sys.exit(0 if not block else 1)
elif mode == "descendant":
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                             creationflags=subprocess.CREATE_NO_WINDOW)
    (folder / "child.json").write_text(json.dumps({"pid": child.pid}))
    time.sleep(30)
elif mode == "orphan":
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                             creationflags=subprocess.CREATE_NO_WINDOW)
    (folder / "child.json").write_text(json.dumps({"pid": child.pid}))
elif mode == "busy":
    duration = float(sys.argv[2]) if len(sys.argv) > 2 else 1
    if not 0 < duration <= 5:
        raise ValueError("Probe must be at most five seconds")
    end = time.monotonic()+duration
    while time.monotonic() < end:
        pass
    print(f"{duration}-second single-core bounded CPU probe complete")
elif mode == "failure":
    sys.exit(7)
elif mode == "nested":
    from customkf.guard import run, Limits
    try:
        run(["tests.guard_probe", "normal"], Limits(memory_mib=128))
    except RuntimeError as exc:
        print(str(exc))
    else:
        sys.exit(1)
else:
    raise ValueError(mode)
