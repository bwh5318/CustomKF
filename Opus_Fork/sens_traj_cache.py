"""Worker: `Opus_Fork.ngv_traj_cache integrate` for a sensitivity variant (`Opus_Fork.sens`).

`sens.install()` first (sub-daily EOP, ERP variant, the named change, `sens.binding()` in `trajectories.json`), then the
unchanged `Opus_Fork.ngv_traj_cache.main`.
"""
from . import sens


def main():
    sens.install()
    from . import ngv_traj_cache
    ngv_traj_cache.main()


if __name__ == "__main__":
    main()
