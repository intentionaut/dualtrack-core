import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import test_parallel  # noqa: E402

IDS = [f"tests.t{i}.Case.test_{i}" for i in range(23)]


class Shards(unittest.TestCase):
    def test_shards_cover_every_id_once(self):
        for n in (1, 3, 4, 7):
            got = [t for i in range(n) for t in test_parallel.select(IDS[::-1], f"{i}/{n}")]
            self.assertEqual(sorted(got), sorted(IDS))

    def test_unset_means_all(self):
        self.assertEqual(sorted(test_parallel.select(IDS, "")), sorted(IDS))

    def test_malformed_raises(self):
        for bad in ("x", "1", "4/4", "-1/4", "1/0", "1/4/2", "a/b", " 1/4"):
            with self.assertRaises(ValueError, msg=bad):
                test_parallel.select(IDS, bad)

    def test_malformed_exits_non_zero(self):
        r = subprocess.run([sys.executable, str(ROOT / "scripts/test_parallel.py")], env={**os.environ, "SHARD": "9/4"},
                           capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("SHARD", r.stdout)


if __name__ == "__main__":
    unittest.main()
