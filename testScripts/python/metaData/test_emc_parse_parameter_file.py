import os
import unittest

from emc_parse_parameter_file import EmcParameterFile


class TestEmcParameterFile(unittest.TestCase):
    def setUp(self):
        # Create a temporary parameter file for testing
        self.test_file = "test_param.m"
        with open(self.test_file, "w") as f:
            f.write("subTomoMeta=emClarity_tutorial\n")
            f.write("fastScratchDisk=/scratch/test\n")
            f.write("nGPUs=2\n")
            f.write("nCpuCores=8\n")
            f.write("PIXEL_SIZE=2.0e-10\n")
            f.write("Cs=2.7e-3\n")
            f.write("VOLTAGE=300e3\n")
            f.write("AMPCONT=0.07\n")
            f.write("symmetry=C1\n")
            f.write("CUTPADDING=15\n")
            f.write("nPeaks=3\n")

    def tearDown(self):
        if os.path.exists(self.test_file):
            os.remove(self.test_file)

    def test_parse_and_access(self):
        emc_file = EmcParameterFile(self.test_file)
        params = emc_file.as_dict()
        self.assertEqual(params['subTomoMeta'], "emClarity_tutorial")
        self.assertEqual(params['nGPUs'], 2)
        self.assertEqual(params['nCpuCores'], 8)
        self.assertEqual(params['PIXEL_SIZE'], 2.0e-10)
        self.assertEqual(params['symmetry'], "C1")
        self.assertEqual(params['CUTPADDING'], 15)
        self.assertEqual(params['nPeaks'], 3)
        # Test default
        self.assertEqual(params['flgCCCcutoff'], 0.0)
        self.assertEqual(params['flgProjectVolumes'], False)

    def test_missing_required(self):
        with open("bad_param.m", "w") as f:
            f.write("nGPUs=2\n")
        with self.assertRaises(ValueError):
            EmcParameterFile("bad_param.m")
        os.remove("bad_param.m")

if __name__ == '__main__':
    unittest.main()
