from pathlib import Path
import math, sys, tempfile, unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from visual_indexing.openclip_encoder import OpenClipEncoder, DIMENSIONS

class VectorTests(unittest.TestCase):
    def test_aggregate_is_normalized_finite_and_512d(self):
        a=[0.0]*DIMENSIONS;b=[0.0]*DIMENSIONS;a[0]=1;b[1]=1
        result=OpenClipEncoder.aggregate([a,b])
        self.assertEqual(len(result),DIMENSIONS);self.assertTrue(all(math.isfinite(x) for x in result))
        self.assertAlmostEqual(sum(x*x for x in result),1,places=5)
    def test_empty_frames_rejected(self):
        with self.assertRaises(ValueError):OpenClipEncoder.aggregate([])
if __name__=="__main__":unittest.main()
