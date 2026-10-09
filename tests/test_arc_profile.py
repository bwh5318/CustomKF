"""Protect the bounded preparation contract; valid cases are checked on real data."""
import unittest
from customkf.stage5_pilot import prepare


class ArcProfileTests(unittest.TestCase):
    def test_existing_profile_does_not_admit_new_cadence(self):
        with self.assertRaisesRegex(ValueError,"five-minute"):
            prepare(profile="nominal-multihour",step_s=600,epoch_count=37)

    def test_new_profile_rejects_unplanned_sampling_or_span(self):
        for step,count in ((300,37),(600,73),(600,12),(900,25)):
            with self.subTest(step=step,count=count):
                with self.assertRaisesRegex(ValueError,"ten-minute"):
                    prepare(profile="nominal-cadence",step_s=step,epoch_count=count)

    def test_unknown_profile_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"Unknown fixture"):
            prepare(profile="unknown")


if __name__=="__main__":unittest.main()
