#!/usr/bin/env bash
# Retired before it was ever run (PROTOCOL.md amendment A3, 8 Oct 2026; Astra N2): it chose campaigns by label, ignored
# the evaluator's exit status, could accept a stale results file and scored dates one at a time. The original is in
# git (commit a879eca; sha256 da86432e79e83f2c7d71e089981148c27a1771c8671e870e1a712d1d8ce92a3f). Use instead:
#   C:/anaconda/python.exe -m Opus_Fork.experiments.networks.score_networks
echo "finish_networks.sh is retired; run: C:/anaconda/python.exe -m Opus_Fork.experiments.networks.score_networks" >&2
exit 1
