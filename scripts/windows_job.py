"""Windows process ownership and serialization for the local launcher."""

import ctypes as ct
from contextlib import contextmanager
from ctypes import wintypes as win


def kernel_function(name, result, *arguments):
    function = getattr(ct.WinDLL("kernel32", use_last_error=True), name)
    function.restype = result
    function.argtypes = arguments
    return function


create_mutex = kernel_function(
    "CreateMutexW", win.HANDLE, win.LPVOID, win.BOOL, win.LPCWSTR
)
wait = kernel_function("WaitForSingleObject", win.DWORD, win.HANDLE, win.DWORD)
release_mutex = kernel_function("ReleaseMutex", win.BOOL, win.HANDLE)
close_handle = kernel_function("CloseHandle", win.BOOL, win.HANDLE)
create_job = kernel_function("CreateJobObjectW", win.HANDLE, win.LPVOID, win.LPCWSTR)
open_job = kernel_function(
    "OpenJobObjectW", win.HANDLE, win.DWORD, win.BOOL, win.LPCWSTR
)
set_job_information = kernel_function(
    "SetInformationJobObject", win.BOOL, win.HANDLE, ct.c_int, win.LPVOID, win.DWORD
)
current_process = kernel_function("GetCurrentProcess", win.HANDLE)
assign_job = kernel_function(
    "AssignProcessToJobObject", win.BOOL, win.HANDLE, win.HANDLE
)
terminate_job = kernel_function("TerminateJobObject", win.BOOL, win.HANDLE, win.UINT)

WAIT_OBJECT_0 = 0
WAIT_ABANDONED = 0x80
WAIT_TIMEOUT = 258
ERROR_FILE_NOT_FOUND = 2
ERROR_ALREADY_EXISTS = 183
JOB_OBJECT_QUERY = 0x0004
JOB_OBJECT_TERMINATE = 0x0008
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9


class BasicLimitInformation(ct.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ct.c_longlong),
        ("PerJobUserTimeLimit", ct.c_longlong),
        ("LimitFlags", win.DWORD),
        ("MinimumWorkingSetSize", ct.c_size_t),
        ("MaximumWorkingSetSize", ct.c_size_t),
        ("ActiveProcessLimit", win.DWORD),
        ("Affinity", ct.c_size_t),
        ("PriorityClass", win.DWORD),
        ("SchedulingClass", win.DWORD),
    ]


class ExtendedLimitInformation(ct.Structure):
    _fields_ = [
        ("BasicLimitInformation", BasicLimitInformation),
        ("IoInfo", ct.c_ulonglong * 6),
        ("ProcessMemoryLimit", ct.c_size_t),
        ("JobMemoryLimit", ct.c_size_t),
        ("PeakProcessMemoryUsed", ct.c_size_t),
        ("PeakJobMemoryUsed", ct.c_size_t),
    ]


@contextmanager
def launcher_lock(name):
    handle = create_mutex(None, False, name)
    if not handle:
        raise ct.WinError(ct.get_last_error())
    try:
        result = wait(handle, 180_000)
        if result == WAIT_TIMEOUT:
            raise RuntimeError("Another startup or shutdown is still in progress.")
        if result not in (WAIT_OBJECT_0, WAIT_ABANDONED):
            raise ct.WinError(ct.get_last_error())
        try:
            yield
        finally:
            release_mutex(handle)
    finally:
        close_handle(handle)


def own_process_tree(name):
    ct.set_last_error(0)
    handle = create_job(None, name)
    error = ct.get_last_error()
    if not handle:
        raise ct.WinError(error)
    try:
        if error == ERROR_ALREADY_EXISTS:
            raise RuntimeError("This checkout already has a launcher process.")
        limits = ExtendedLimitInformation()
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not set_job_information(
            handle,
            JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ct.byref(limits),
            ct.sizeof(limits),
        ) or not assign_job(handle, current_process()):
            raise ct.WinError(ct.get_last_error())
    except BaseException:
        close_handle(handle)
        raise
    # The supervisor owns this non-inheritable handle until it exits. Its child
    # processes join the job automatically, including the venv shim's child.


def managed_job(name, *, stop=False):
    access = JOB_OBJECT_TERMINATE if stop else JOB_OBJECT_QUERY
    handle = open_job(access, False, name)
    if not handle:
        error = ct.get_last_error()
        if error == ERROR_FILE_NOT_FOUND:
            return False
        raise ct.WinError(error)
    try:
        if stop and not terminate_job(handle, 0):
            raise ct.WinError(ct.get_last_error())
        return True
    finally:
        close_handle(handle)
