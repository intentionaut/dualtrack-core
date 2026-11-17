"""request.py drafts a request for the kit's author and sends nothing by itself."""
import os
import pathlib
import sys
import unittest
import urllib.parse
from unittest import mock

KIT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "scripts"))
import loop_lib  # noqa: E402
import request  # noqa: E402


class Request(unittest.TestCase):
    def run_req(self, *argv):
        with mock.patch("webbrowser.open", return_value=True) as opened, mock.patch("sys.stdout"):
            code = request.main(list(argv))
        return code, opened

    def test_opens_a_filled_issue_with_only_the_words_and_version(self):
        code, opened = self.run_req("--share", "issue", "Take comments on pull requests")
        self.assertEqual(code, 0)
        q = urllib.parse.parse_qs(urllib.parse.urlparse(opened.call_args[0][0]).query)
        self.assertEqual(q["title"], ["Kit request: Take comments on pull requests"])
        self.assertEqual(q["body"], [f"Take comments on pull requests\n\nDualtrack {request.version()}\n"])

    def test_email_goes_to_the_kits_address(self):
        _, opened = self.run_req("--share", "email", "x")
        self.assertTrue(opened.call_args[0][0].startswith(f"mailto:{request.destinations()['email']}?"))

    def test_nothing_to_ask_sends_nothing(self):
        with mock.patch("sys.stdin.isatty", return_value=False):
            code, opened = self.run_req("--share", "issue")
        self.assertEqual(code, 2); opened.assert_not_called()

    def test_long_requests_get_a_short_title(self):
        self.assertLessEqual(len(request.title("word " * 40)), len("Kit request: ") + 60)

    def test_a_stopped_run_offers_the_request_and_a_good_one_does_not(self):
        stopped = loop_lib.morning("", "stopped: could not push", "2026-11-08", kit="/k")
        self.assertIn("python3 /k/scripts/request.py", stopped)
        self.assertNotIn("request.py", loop_lib.morning("", "opened: x", "2026-11-08", kit="/k"))


if __name__ == "__main__":
    unittest.main()
