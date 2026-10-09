"""RINEX 3 header-information events (flag 4) in `customkf.rinex.epochs` (29 Sep 2026 defect fix).

    C:\\anaconda\\python.exe -m unittest tests.test_rinex_events -v

An event is accepted only when it changes nothing: comments, or a SYS / PHASE SHIFT declaring no correction (empty or
zero shift, the header's own rule). Any other content, a non-zero shift, or other event flags still refuse.
Synthetic streams only.
"""
import io
import unittest

from customkf.rinex import Header, epochs

TYPES = ["C1C", "L1C"]


def obs(value):
    return f"{value:14.3f}  "


def stream(event_rows, flag=4):
    lines = ["> 2026 06 20 00 00  0.0000000  0  1\n", "G01" + obs(2.1e7) + obs(1.1e8) + "\n",
             f"> 2026 06 20 02 00  0.0000000  {flag}{len(event_rows):3d}\n", *event_rows,
             "> 2026 06 20 02 00 30.0000000  0  1\n", "G01" + obs(2.1e7) + obs(1.1e8) + "\n"]
    return io.StringIO("".join(lines))


def label(body, name):
    return body.ljust(60) + name + "\n"


def read(rows, flag=4):
    meta = Header(3.04, types={"G": TYPES})
    return list(epochs(stream(rows, flag), meta)), meta


class HeaderEvents(unittest.TestCase):
    def test_zero_phase_shift_event_accepted_and_recorded(self):
        """The YELL00CAN case of 2026-06-20 and 06-23."""
        out, meta = read([label("E L6C  0.00000", "SYS / PHASE SHIFT")])
        self.assertEqual(len(out), 2)
        self.assertEqual(len(meta.comment_events), 1)
        self.assertIn("SYS / PHASE SHIFT", meta.comment_events[0]["lines"][0])

    def test_empty_phase_shift_and_comments_accepted(self):
        out, meta = read([label("G L1C", "SYS / PHASE SHIFT"), label("receiver restarted", "COMMENT")])
        self.assertEqual(len(out), 2)

    def test_comment_only_event_unchanged(self):
        out, meta = read([label("just a note", "COMMENT")])
        self.assertEqual(len(out), 2)

    def test_nonzero_phase_shift_refused(self):
        with self.assertRaisesRegex(ValueError, "RINEX event 4"):
            read([label("G L1C -0.25000", "SYS / PHASE SHIFT")])

    def test_equipment_change_refused(self):
        with self.assertRaisesRegex(ValueError, "RINEX event 4"):
            read([label("12345               TRM59800.00     NONE", "ANT # / TYPE")])

    def test_mixed_event_refused(self):
        with self.assertRaisesRegex(ValueError, "RINEX event 4"):
            read([label("E L6C  0.00000", "SYS / PHASE SHIFT"), label("0.1 0.0 0.0", "ANTENNA: DELTA H/E/N")])

    def test_malformed_shift_refused(self):
        with self.assertRaisesRegex(ValueError, "RINEX event 4"):
            read([label("E L6C  abc", "SYS / PHASE SHIFT")])

    def test_other_event_flags_still_refused(self):
        for flag in (2, 3, 5):
            with self.subTest(flag=flag), self.assertRaisesRegex(ValueError, f"RINEX event {flag}"):
                read([label("E L6C  0.00000", "SYS / PHASE SHIFT")], flag=flag)


if __name__ == "__main__":
    unittest.main()
