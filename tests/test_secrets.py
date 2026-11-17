"""The secret scan: live token shapes are caught, and the look-alikes in docs and examples are not."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import loop_lib

CAUGHT = [
    "glpat-" + "a" * 20,
    "npm_" + "b" * 36,
    "ey" + "J" + "hbGciOiJIUzI1NiJ9." + "ey" + "J" + "zdWIiOiIxMjM0NTY3ODkwIn0." + "d" * 30,
    "https://hooks.slack.com/services/T0AAAAAAA/B0BBBBBBB/" + "c" * 24,
    "postgres://app:" + "Hx9kq2Lm" + "@db.example.com/main",
    "mongodb+srv://u:" + "R3al_pw!" + "@cluster.example.net",
    "Authorization: " + "Basic " + "dXNlcjpwYXNzd29yZDEyMzQ1Ng==",
]
KEPT = [
    "postgres://localhost/app",
    "postgresql://u@host/db",
    "postgres://user:password@localhost/db",
    "postgres://user:${DB_PASS}@host/db",
    "mysql://root:<password>@host",
    "redis://:xxx@cache",
    "Authorization: Bearer $TOKEN",
    "see eyJ in the docs",
    "version 1.2.3",
    "npm_config_cache=/tmp/npm",
    "npm_" + "b" * 12,
    "https://hooks.slack.com/services/T0AAAAAAA/B0BBBBBBB/xxxx",
    "postgres://postgres:postgres@localhost:5432/test",
    "Authorization: Bearer <token>",
]


class Secrets(unittest.TestCase):
    def test_kept_cases_pass(self):
        for text in KEPT:
            self.assertEqual(loop_lib.leaks(text), [], text)

    def test_live_token_shapes_are_caught(self):
        for text in CAUGHT:
            self.assertEqual(loop_lib.leaks(text), ["a secret"], text)


if __name__ == "__main__":
    unittest.main()
