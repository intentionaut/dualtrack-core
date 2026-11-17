"""Public numbers: GitHub and package downloads, free, each with its source and window."""
import pathlib
import sys
import unittest

KIT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "scripts"))
import loop_lib
import public_source


def fake_gh(path):
    if path.endswith("traffic/clones"):
        raise RuntimeError("HTTP 403: Must have push access")
    if path.endswith("traffic/views"):
        return {"count": 40, "uniques": 12}
    return {"stargazers_count": 31, "forks_count": 4}


class Public(unittest.TestCase):
    def test_numbers_name_their_source_and_a_failed_read_is_listed(self):
        urls = []
        fetch = lambda u: (urls.append(u), {"downloads": 900} if "npmjs" in u else {"data": {"last_week": 55}})[1]
        md = public_source.read("**Packages:** npm:kernic, pypi:dualtrack, cargo:x, npm:bad name\n", "2026-11-12", fake_gh, fetch)
        self.assertIn("- GitHub stars: 31 (", md)
        self.assertIn("- GitHub views: 40, 12 unique (", md)
        self.assertIn("- npm downloads of kernic: 900 (https://api.npmjs.org/downloads/point/last-week/kernic, last 7 days)", md)
        self.assertIn("- pypi downloads of dualtrack: 55 (", md)
        self.assertIn("Could not be read:\n- GitHub clones, HTTP 403", md)
        self.assertEqual(len(urls), 2)  # an unknown registry or an odd name is never fetched
        self.assertEqual(loop_lib.leaks(md), [])

    def test_no_packages_and_no_github_says_so(self):
        def down(path):
            raise RuntimeError("gh: not signed in")
        md = public_source.read("", "2026-11-12", down, lambda u: self.fail("fetched"))
        self.assertIn("- none found", md)
        self.assertIn("- GitHub repo, gh: not signed in", md)


if __name__ == "__main__":
    unittest.main()
