"""Which other processes can interfere with a guarded campaign (user decision, 3 Oct 2026).

From 20 Sep 2026 the fork guard and `Opus_Fork.run_fit_elev` refused to start while *any* Python process existed. A
bare guarded job had slipped into the gap between two workers of a campaign, and the campaign aborted. The campaign
lease (29 Sep) now protects that gap for lease-holding controllers.

The user narrowed the check to **this project's guard and campaign-controller processes**: Python running
`-m customkf.guard`, `-m Opus_Fork.guard` or `-m Opus_Fork.run_fit*`. Other Python is governed by the hardware rules
(the machine-wide usage ceilings and the memory reserve) instead. That covers other projects' Python and this
project's unguarded analyses and tests.

A guarded worker exists only under such a guard or controller, so it is covered through its parent. A controller that
imports a guard in-process under another module name (the older `claude.experiments.*` controllers) is not counted
between its workers. Those controllers do not hold the campaign lease either, so they were already unprotected against
lease-holding work. The user accepted that a broken run is restarted (3 Oct 2026).
"""
import os
import re

import psutil

CAMPAIGN_MODULE = re.compile(r"^(customkf\.guard|Opus_Fork\.guard|Opus_Fork\.run_fit\w*)$")
_TAKES_VALUE = frozenset("WX")  # interpreter options with an argument; -m and -c are handled separately


def module_of(cmdline):
    """The `-m` module of a Python command line, or None (a script, `-c`, or nothing).

    Follows the interpreter's option rules: options come before the script or module, short options may be clustered
    (`-um mod`, `-mmod`), and `-W`/`-X` take a value. Arguments after the script belong to the script, so a `-m` there
    is not a module.
    """
    args = [str(a) for a in (cmdline or [])][1:]
    i = 0
    while i < len(args):
        arg = args[i]
        i += 1
        if arg == "--" or not arg.startswith("-") or arg == "-":
            return None
        if arg.startswith("--"):
            if arg == "--check-hash-based-pycs":
                i += 1
            continue
        for k, flag in enumerate(arg[1:], 1):
            if flag in "mc" or flag in _TAKES_VALUE:
                value = arg[k+1:]
                if not value:
                    value = args[i] if i < len(args) else None
                    i += 1
                if flag == "m":
                    return value
                if flag == "c":
                    return None
                break
    return None


def campaign_processes(exclude=()):
    """PIDs of other running guard or campaign-controller Python processes of this project.

    Processes whose command line cannot be read (another user, a protected process) are not this project's and are not
    counted.
    """
    exclude = set(exclude) | {os.getpid()}
    found = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        info = p.info
        if info["pid"] in exclude or "python" not in (info["name"] or "").lower():
            continue
        module = module_of(info.get("cmdline"))
        if module and CAMPAIGN_MODULE.match(module):
            found.append(info["pid"])
    return found
