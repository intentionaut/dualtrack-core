import sys, unittest
sys.path.insert(0, sys.argv[1]); sys.argv = sys.argv[:1]
from textkit import table
class Accept(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(table([{"a": 1, "b": 2}]).strip().splitlines(), ["| a | b |", "| --- | --- |", "| 1 | 2 |"])
    def test_order_and_missing(self):
        out = table([{"a": 1}, {"b": 2, "a": 3}]).strip().splitlines()
        self.assertEqual(out[0], "| a | b |"); self.assertEqual(out[2], "| 1 |  |"); self.assertEqual(out[3], "| 3 | 2 |")
    def test_pipe_escaped(self):
        self.assertIn("x \\| y", table([{"a": "x | y"}]))
    def test_empty(self):
        self.assertEqual(table([]), "")
unittest.main()
