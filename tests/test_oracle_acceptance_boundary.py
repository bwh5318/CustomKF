"""Oracle acceptance boundary (Astra PI-11, 8 Oct 2026): the checker's process status follows its scientific result,
and the oracle's SP3 reader refuses malformed products instead of reading them silently.

    C:\\anaconda\\python.exe -m unittest tests.test_oracle_acceptance_boundary -v
"""
from pathlib import Path
import tempfile
import unittest

from validation.oracle import metrics as O1
from validation.oracle.check import exit_status

HEADER = ["#dP2026  7 23  0  0  0.00000000       2 ORBIT IGc20 FIT OPUS",
          "%c G  cc GPS ccc cccc cccc cccc cccc ccccc ccccc ccccc ccccc",
          "%c cc cc ccc ccc cccc cccc cccc cccc ccccc ccccc ccccc ccccc"]
EPOCH = "*  2026  7 23  0  0  0.00000000"
G01 = "PG01 -21084.530291 -15901.577372  -3254.523586 999999.999999"
G02 = "PG02 -17218.395888 -16373.870828 -12100.819633 999999.999999"


class ExitStatus(unittest.TestCase):
    def test_only_an_explicit_pass_exits_zero(self):
        self.assertEqual(exit_status(dict(passed=True)), 0)
        for report in (dict(passed=False), dict(), dict(passed="yes"), dict(passed=1)):
            self.assertEqual(exit_status(report), 1, report)


class StrictReader(unittest.TestCase):
    def read(self, lines):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"x.SP3"
            path.write_text("\n".join(lines+["EOF"])+"\n")
            return O1.read_sp3(path)

    def test_well_formed_product_reads(self):
        values = self.read(HEADER+[EPOCH, G01, G02])
        self.assertEqual(len(values), 2)

    def test_sp3a_unspecified_time_system_reads(self):
        header = [HEADER[0], "%c cc cc ccc ccc cccc cccc cccc cccc ccccc ccccc ccccc ccccc"]
        self.assertEqual(len(self.read(header+[EPOCH, G01])), 1)

    def test_malformed_products_refused(self):
        cases = {"duplicate": HEADER+[EPOCH, G01, G01],
                 "non-GPS time system": [HEADER[0], HEADER[1].replace("GPS", "UTC")]+[EPOCH, G01],
                 "position before epoch": HEADER+[G01, EPOCH, G02],
                 "non-finite": HEADER+[EPOCH, G01.replace("-21084.530291", "          nan")]}
        for name, lines in cases.items():
            with self.subTest(name), self.assertRaises(ValueError):
                self.read(lines)


if __name__ == "__main__":
    unittest.main()
