"""Worker: `Opus_Fork.ngv_traj_cache integrate` for a elevation variant (`Opus_Fork.elev`).

`elev.install()` first (sub-daily EOP, ERP variant, the named change, `elev.binding()` in `trajectories.json`), then the
unchanged `Opus_Fork.ngv_traj_cache.main`.
"""
from . import elev


def main():
    elev.install()
    from . import ngv_traj_cache
    ngv_traj_cache.main()


if __name__ == "__main__":
    main()
