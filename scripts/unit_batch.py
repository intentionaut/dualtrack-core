#!/usr/bin/env python3
"""Run the given test ids like `python3 -m unittest <ids>`, then print each test's seconds on one last line.

test_parallel.py starts this once per batch. The "::durations:: {...}" line feeds `test_parallel.py --record`;
the rest of the output is plain unittest output.
"""
import json
import os
import sys
import time
import unittest


class Timed(unittest.TextTestResult):
    seconds = {}

    def startTest(self, test):
        self._t0 = time.perf_counter()
        super().startTest(test)

    def stopTest(self, test):
        Timed.seconds[test.id()] = round(time.perf_counter() - self._t0, 3)
        super().stopTest(test)


if __name__ == "__main__":
    sys.path[0] = os.getcwd()  # as `python3 -m unittest` has it: the repo root first, not this script's folder
    prog = unittest.main(module=None, argv=["unit_batch", *sys.argv[1:]], testRunner=unittest.TextTestRunner(resultclass=Timed), exit=False)
    print("::durations:: " + json.dumps(Timed.seconds), file=sys.stderr)
    sys.exit(0 if prog.result.wasSuccessful() else 1)
