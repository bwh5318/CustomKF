"""Opus_Fork.prepare.station_markers: stations beyond the frozen 25 are given as nine-character markers (5 Oct 2026,
network tests); four-character names resolve exactly as before.

    C:\\anaconda\\python.exe -m unittest tests.test_prepare_markers -v
"""
import unittest

from Opus_Fork.prepare import STATIONS, station_markers


class StationMarkers(unittest.TestCase):
    def test_four_character_names_resolve_as_before(self):
        names = list(STATIONS)
        self.assertEqual(station_markers(names), {s: STATIONS[s] for s in names})

    def test_nine_character_markers_and_order(self):
        got = station_markers(["MOBS00AUS", "BRUX", "UNSA00ARG", "HOB200AUS"])
        self.assertEqual(list(got), ["MOBS", "BRUX", "UNSA", "HOB2"])
        self.assertEqual(got["MOBS"], "MOBS00AUS")
        self.assertEqual(got["BRUX"], "BRUX00BEL")
        self.assertEqual(got["HOB2"], "HOB200AUS")

    def test_unknown_four_character_name_is_refused(self):
        with self.assertRaises(KeyError):
            station_markers(["MOBS"])


if __name__ == "__main__":
    unittest.main()
