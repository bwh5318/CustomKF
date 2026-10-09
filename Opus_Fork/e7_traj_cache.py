"""Worker: trajectory cache with ECOM-7 and a named ERP + thrust variant (`Opus_Fork.e7`).

    ... -- Opus_Fork.e7_traj_cache integrate <claude.roadmap.traj_cache arguments>

Runs `Opus_Fork.ngv_traj_cache.main` after `e7.install()`: count-7 model, 7-element parameters,
per-satellite ERP + thrust, and `force_model` = `e7.binding()` in `trajectories.json`.
"""
from . import e7


def main():
    e7.install()
    from . import ngv_traj_cache
    ngv_traj_cache.main()


if __name__ == "__main__":
    main()
