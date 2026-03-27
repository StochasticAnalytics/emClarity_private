import unittest

from emc_type_traits import EmcTypeTraits


class TestEmcTypeTraits(unittest.TestCase):
    def setUp(self):
        self.traits = EmcTypeTraits()

    def test_assert_numeric_scalar(self):
        self.assertTrue(self.traits.assert_numeric(5))
        self.assertTrue(self.traits.assert_numeric(3.14))
        with self.assertRaises(ValueError):
            self.traits.assert_numeric("not_a_number")

    def test_assert_numeric_list(self):
        self.assertTrue(self.traits.assert_numeric([1, 2, 3]))
        with self.assertRaises(ValueError):
            self.traits.assert_numeric([1, "bad", 3])

    def test_assert_numeric_length(self):
        self.assertTrue(self.traits.assert_numeric([1, 2], expected_length=2))
        with self.assertRaises(ValueError):
            self.traits.assert_numeric([1, 2], expected_length=3)

    def test_assert_numeric_range(self):
        self.assertTrue(self.traits.assert_numeric(5, value_range=[0, 10]))
        with self.assertRaises(ValueError):
            self.traits.assert_numeric(15, value_range=[0, 10])

    def test_assert_boolean(self):
        self.assertTrue(self.traits.assert_boolean(True))
        self.assertTrue(self.traits.assert_boolean(False))
        self.assertTrue(self.traits.assert_boolean(1))
        self.assertTrue(self.traits.assert_boolean(0))
        # Should not raise, but if you want strict bool, uncomment below
        # with self.assertRaises(ValueError):
        #     self.traits.assert_boolean("not_bool")

    def test_assert_string_value(self):
        self.assertTrue(self.traits.assert_string_value("A", ["A", "B"]))
        self.assertTrue(self.traits.assert_string_value("a", ["A", "B"]))
        with self.assertRaises(ValueError):
            self.traits.assert_string_value("C", ["A", "B"])

    def test_assert_deprecated_substitution(self):
        params = {"old": 1}
        result = self.traits.assert_deprecated_substitution(params, "old", "new")
        self.assertIn("new", result)
        self.assertNotIn("old", result)
        self.assertEqual(result["new"], 1)

if __name__ == '__main__':
    unittest.main()
