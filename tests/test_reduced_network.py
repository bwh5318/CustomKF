"""Independent small-oracle and scale-bound checks for estimate-only QR."""
import unittest
import numpy as np
from customkf.network_square_root import Block, eliminated_qr
from customkf.reduced_network import reduced_qr, budget


class ReducedNetworkTests(unittest.TestCase):
    def fixture(self,count=3,local=4,retained=7):
        rng=np.random.default_rng(61039);blocks=[]
        truth=rng.normal(size=retained+count*local)
        for i in range(count):
            g=rng.normal(size=(local+10,retained));l=rng.normal(size=(local+10,local))
            y=g@truth[:retained]+l@truth[retained+i*local:retained+(i+1)*local]
            blocks.append(Block(g,l,y,np.exp(rng.uniform(-2,2,len(y)))))
        return blocks,(np.eye(retained),truth[:retained],np.ones(retained)*3),truth

    def test_matches_full_covariance_oracle(self):
        b,c,_=self.fixture();new=reduced_qr(b,c);old=eliminated_qr(b,c)
        np.testing.assert_allclose(new.estimate,old.estimate,rtol=0,atol=1e-12)
        np.testing.assert_allclose(new.retained_covariance,old.covariance[:7,:7],rtol=2e-12,atol=1e-12)

    def test_local_clock_count_does_not_allocate_full_covariance(self):
        b,c,truth=self.fixture(count=25,local=40,retained=4)
        with self.assertRaises(ValueError):eliminated_qr(b,c)
        result=reduced_qr(b,c)
        self.assertEqual(result.retained_covariance.shape,(4,4))
        np.testing.assert_allclose(result.estimate,truth,rtol=0,atol=1e-12)

    def test_rank_deficiency_is_not_hidden(self):
        b,c,_=self.fixture()
        for block in b:block.retained[:,0]=0
        c[0][:,0]=0
        with self.assertRaises(ValueError):reduced_qr(b,c)

    def test_budget_and_bad_weights(self):
        b,c,_=self.fixture();b[0].sigma[0]=0
        with self.assertRaises(ValueError):budget(b,c)
        b,c,_=self.fixture(count=100,local=40,retained=900)
        with self.assertRaises(ValueError):budget(b,c)


if __name__=="__main__":unittest.main()
