import unittest
from calculator import add
class CalculatorTests(unittest.TestCase):
    def test_positive(self): self.assertEqual(add(2,3),5)
    def test_negative(self): self.assertEqual(add(-3,1),-2)
    def test_float(self): self.assertAlmostEqual(add(1.5,2.25),3.75)
