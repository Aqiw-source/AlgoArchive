"""Run regression tests against isolated temporary data, never the user's data."""
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
print("AlgoArchive self-check / 独立临时目录自检", flush=True)
suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
