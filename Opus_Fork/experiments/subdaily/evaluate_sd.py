"""`Opus_Fork.evaluate` with sub-daily-EOP fits scored as their Earth-fixed products (`sd_scoring`). Same arguments."""
from Opus_Fork.experiments.subdaily import sd_scoring

if __name__ == "__main__":
    sd_scoring.install()
    from Opus_Fork import evaluate
    evaluate.main()
