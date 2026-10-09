"""Worker: `Opus_Fork.ngv_traj_cache integrate` with the IERS 2010 sub-daily EOP (`Opus_Fork.sdeop`).

    ... -- Opus_Fork.sd_traj_cache integrate <Opus_Fork.ngv_traj_cache arguments>

`sdeop.install()` first (sub-daily EOP in this process, ERP variant, `sdeop.binding()` recorded in
`trajectories.json`), then the unchanged `Opus_Fork.ngv_traj_cache.main`.
"""
from . import sdeop


def main():
    sdeop.install()
    from . import ngv_traj_cache
    ngv_traj_cache.main()


if __name__ == "__main__":
    main()
