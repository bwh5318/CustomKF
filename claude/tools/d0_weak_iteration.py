"""Weak-orbit-prior D0 iteration: Astra's unchanged iteration logic, weak-prior pilot.

`claude.tools.d0_iteration` is pinned and must not be edited, so this module binds
`WeakD0Pilot` into it and calls its `main()` unchanged. Nothing else differs: the
same Jacobian, reduced QR, 1/.5/.25/.125 line search, force-inclusive stopping rule,
hash checks and checkpoint format. Reusing the module rather than copying it is what
guarantees there is no logic drift between the nominal and weak-prior runs.

This follows the existing project pattern of binding a pilot factory into a guarded
worker (`claude.tools.d0_step` does the same with `ablation_step.build_pilot`).
"""
from claude.tools import d0_iteration
from claude.tools.d0_weak_pilot import WeakD0Pilot

d0_iteration.D0Pilot = WeakD0Pilot

if __name__ == "__main__":
    d0_iteration.main()
