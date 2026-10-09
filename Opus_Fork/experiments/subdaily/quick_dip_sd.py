"""`Opus_Fork.experiments.ecom7.quick_dip` with sub-daily-EOP fits presented as their Earth-fixed products. Same arguments.

quick_dip labels its second arm "E7"; here that arm is the sub-daily-EOP fit.
"""
from Opus_Fork.experiments.subdaily import sd_scoring

if __name__ == "__main__":
    sd_scoring.install()
    from Opus_Fork.experiments.ecom7 import quick_dip
    quick_dip.main()
