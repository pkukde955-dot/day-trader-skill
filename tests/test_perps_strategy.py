import unittest
from decimal import Decimal
from _load import load
s=load("trader-perps","strategy")

def bars(rows):
 return [{"open":Decimal(str(o)),"high":Decimal(str(h)),"low":Decimal(str(l)),"close":Decimal(str(c)),"volume":Decimal("1")} for o,h,l,c in rows]

class StrategyTests(unittest.TestCase):
 def test_neutral_bias_blocks(self):
  self.assertEqual(s.detect_setup(bars([(100,102,98,100)]*20),bars([(100,102,98,100)]*20),"100")["signal"],"NONE")
 def test_insufficient_history_blocks(self):
  self.assertEqual(s.detect_setup([],[],"100")["reason"],"insufficient_history")
 def test_risk_size_margin_cap_and_step(self):
  self.assertEqual(s.size_for_risk("1000","100","99","0.01","0.001","0.001","2","5"),Decimal("4.000"))
 def test_excess_risk_rejected(self):
  with self.assertRaises(ValueError): s.size_for_risk("1000","100","99","0.10","0.001","0.001","2","5")
 def test_below_minimum_returns_zero(self):
  self.assertEqual(s.size_for_risk("1000","100","99","0.0005","1","1","2","5"),Decimal("0"))

if __name__=="__main__": unittest.main()
