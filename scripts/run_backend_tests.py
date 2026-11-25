"""Run the backend suite and report its ten slowest test cases."""
from __future__ import annotations

import time
import unittest
import os
from pathlib import Path
import sys


class TimingResult(unittest.TextTestResult):
    def startTest(self, test):
        self._test_started_at = time.perf_counter()
        super().startTest(test)

    def stopTest(self, test):
        elapsed = time.perf_counter() - self._test_started_at
        self.slowest_tests.append((elapsed, self.getDescription(test)))
        super().stopTest(test)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.slowest_tests = []


class TimingRunner(unittest.TextTestRunner):
    resultclass = TimingResult


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    sys.path.insert(0, str(root))
    suite = unittest.defaultTestLoader.discover("tests")
    result = TimingRunner(verbosity=2).run(suite)
    print("\nSlowest 10 backend tests:")
    for elapsed, name in sorted(result.slowest_tests, reverse=True)[:10]:
        print(f"{elapsed:7.2f}s  {name}")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
