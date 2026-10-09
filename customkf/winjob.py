"""Small Windows Job Object binding. Fail closed on every setup error.

Uses documented Win32 APIs; no pywin32 installation. Configure before resuming
the suspended worker, and never grant breakaway or inherit the job handle.
"""
import ctypes as C
from ctypes import wintypes as W
import os
import subprocess

if os.name != "nt":
    raise RuntimeError("The bounded runner requires Windows Job Objects")

K = C.WinDLL("kernel32", use_last_error=True)
SIZE = C.c_size_t
HANDLE = W.HANDLE


class BasicLimits(C.Structure):
    _fields_ = [("process_time", C.c_longlong), ("job_time", C.c_longlong),
                ("flags", W.DWORD), ("min_ws", SIZE), ("max_ws", SIZE),
                ("active_limit", W.DWORD), ("affinity", SIZE),
                ("priority", W.DWORD), ("scheduling", W.DWORD)]


class IO(C.Structure):
    _fields_ = [(n, C.c_ulonglong) for n in
                ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]


class ExtendedLimits(C.Structure):
    _fields_ = [("basic", BasicLimits), ("io", IO),
                ("process_memory", SIZE), ("job_memory", SIZE),
                ("peak_process_memory", SIZE), ("peak_job_memory", SIZE)]


class CpuLimits(C.Structure):
    _fields_ = [("flags", W.DWORD), ("rate", W.DWORD)]


class Accounting(C.Structure):
    _fields_ = [(n, C.c_longlong) for n in ("user", "kernel", "period_user", "period_kernel")] + [
        (n, W.DWORD) for n in ("faults", "total", "active", "terminated")]


class Startup(C.Structure):
    _fields_ = [("cb", W.DWORD), ("reserved", W.LPWSTR), ("desktop", W.LPWSTR),
                ("title", W.LPWSTR)] + [(n, W.DWORD) for n in
                ("x", "y", "xs", "ys", "xc", "yc", "fill", "flags")] + [
                ("show", W.WORD), ("reserved2_size", W.WORD), ("reserved2", C.c_void_p),
                ("stdin", HANDLE), ("stdout", HANDLE), ("stderr", HANDLE)]


class ProcessInfo(C.Structure):
    _fields_ = [("process", HANDLE), ("thread", HANDLE), ("pid", W.DWORD), ("tid", W.DWORD)]


def bind(name, args, result=W.BOOL):
    fn = getattr(K, name)
    fn.argtypes, fn.restype = args, result
    return fn


create_job = bind("CreateJobObjectW", [C.c_void_p, W.LPCWSTR], HANDLE)
set_info = bind("SetInformationJobObject", [HANDLE, C.c_int, C.c_void_p, W.DWORD])
query_info = bind("QueryInformationJobObject", [HANDLE, C.c_int, C.c_void_p, W.DWORD, C.c_void_p])
assign = bind("AssignProcessToJobObject", [HANDLE, HANDLE])
is_in_job = bind("IsProcessInJob", [HANDLE, HANDLE, C.POINTER(W.BOOL)])
terminate_job = bind("TerminateJobObject", [HANDLE, W.UINT])
terminate_process = bind("TerminateProcess", [HANDLE, W.UINT])
close_handle = bind("CloseHandle", [HANDLE])
resume = bind("ResumeThread", [HANDLE], W.DWORD)
wait = bind("WaitForSingleObject", [HANDLE, W.DWORD], W.DWORD)
exit_code = bind("GetExitCodeProcess", [HANDLE, C.POINTER(W.DWORD)])
create_mutex = bind("CreateMutexW", [C.c_void_p, W.BOOL, W.LPCWSTR], HANDLE)
create_process = bind("CreateProcessW", [W.LPCWSTR, W.LPWSTR, C.c_void_p,
    C.c_void_p, W.BOOL, W.DWORD, C.c_void_p, W.LPCWSTR, C.POINTER(Startup), C.POINTER(ProcessInfo)])


def check(ok):
    if not ok:
        raise C.WinError(C.get_last_error())
    return ok


class Job:
    def __init__(self, memory_bytes, cpu_percent, cpus):
        self.handle = check(create_job(None, None))
        try:
            limits = ExtendedLimits()
            # Kill-on-close, aggregate private commit, priority, affinity, process count.
            limits.basic.flags = 0x2000 | 0x200 | 0x20 | 0x10 | 0x8
            limits.basic.priority = 0x4000  # BELOW_NORMAL_PRIORITY_CLASS
            limits.basic.affinity = sum(1 << cpu for cpu in cpus)
            limits.basic.active_limit = 4
            limits.job_memory = memory_bytes
            check(set_info(self.handle, 9, C.byref(limits), C.sizeof(limits)))
            cpu = CpuLimits(0x1 | 0x4, round(cpu_percent * 100))
            check(set_info(self.handle, 15, C.byref(cpu), C.sizeof(cpu)))
            actual, actual_cpu = self.limits(), self.cpu_limits()
            if (actual.basic.flags & limits.basic.flags != limits.basic.flags
                    or actual.job_memory != memory_bytes
                    or actual.basic.affinity != limits.basic.affinity
                    or actual.basic.priority != limits.basic.priority
                    or actual.basic.active_limit != 4
                    or actual_cpu.flags != cpu.flags or actual_cpu.rate != cpu.rate):
                raise RuntimeError("Windows did not retain the requested resource limits")
        except BaseException:
            self.close()
            raise

    def query(self, kind, cls):
        value = cls()
        check(query_info(self.handle, kind, C.byref(value), C.sizeof(value), None))
        return value

    def limits(self):
        return self.query(9, ExtendedLimits)

    def cpu_limits(self):
        return self.query(15, CpuLimits)

    def accounting(self):
        return self.query(1, Accounting)

    def terminate(self, code=125):
        check(terminate_job(self.handle, code))

    def close(self):
        if self.handle:
            close_handle(self.handle)
            self.handle = None


class Worker:
    def __init__(self, job, command, env, cwd, stdout, stderr, stdin):
        import msvcrt
        self.info = ProcessInfo()
        self.closed = False
        startup = Startup()
        startup.cb, startup.flags = C.sizeof(startup), 0x100  # USESTDHANDLES
        files = [stdin, stdout, stderr]
        handles = [msvcrt.get_osfhandle(f.fileno()) for f in files]
        startup.stdin, startup.stdout, startup.stderr = handles
        old = [os.get_handle_inheritable(h) for h in handles]
        try:
            for h in handles:
                os.set_handle_inheritable(h, True)
            environment = C.create_unicode_buffer("\0".join(
                f"{key}={value}" for key, value in sorted(env.items(), key=lambda kv: kv[0].upper())) + "\0\0")
            command_line = C.create_unicode_buffer(subprocess.list2cmdline(command))
            flags = 0x4 | 0x400 | 0x08000000 | 0x4000  # SUSPENDED, UNICODE, NO_WINDOW, BELOW_NORMAL
            check(create_process(command[0], command_line, None, None, True,
                                 flags, environment, str(cwd), C.byref(startup), C.byref(self.info)))
            check(assign(job.handle, self.info.process))
            member = W.BOOL()
            check(is_in_job(self.info.process, job.handle, C.byref(member)))
            if not member.value:
                raise RuntimeError("Worker was not assigned to resource job")
            if resume(self.info.thread) == 0xFFFFFFFF:
                raise C.WinError(C.get_last_error())
        except BaseException:
            if self.info.process:
                terminate_process(self.info.process, 126)
            self.close()
            raise
        finally:
            for h, inherited in zip(handles, old):
                os.set_handle_inheritable(h, inherited)

    def code(self):
        state = wait(self.info.process, 0)
        if state == 258:  # WAIT_TIMEOUT
            return None
        if state != 0:
            raise C.WinError(C.get_last_error())
        value = W.DWORD()
        check(exit_code(self.info.process, C.byref(value)))
        return int(value.value)

    def close(self):
        if not self.closed:
            for h in (self.info.thread, self.info.process):
                if h:
                    close_handle(h)
            self.closed = True
