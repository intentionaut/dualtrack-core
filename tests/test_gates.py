"""One gate vocabulary: every outcome a run can end on maps to one gate state, one exit code and one next step.

The scan reads daily_loop.sh and run.sh as text, so a stop added later without a row in loop_lib.GATES fails here.
"""
import json
import os
import pathlib
import re
import subprocess
import sys
import unittest

KIT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "scripts"))
import dashboard
import dashboard_server
import handoff
try:
    import scratch
except ImportError:  # run as tests.test_x from the repo root
    from tests import scratch
import loop_lib
import stats
import tamper

STATES = {"pass", "failed", "waiting_for_decision", "blocked", "safety_stop"}

# Outcomes whose words are built from a command's output; the scan cannot run the command, so it is given what it prints.
SAMPLES = {
    'stopped: $why': ["stopped: Claude Code is not logged in"],  # daily_loop.sh: the credential check
    '$why': [tamper.message(["scripts/x.py"])],  # daily_loop.sh: the tamper check prints tamper.py's message
    'stopped: $(cat "$RUN/timeout.txt")': ["stopped: a test or setup command ran longer than 20 minutes and was stopped. Find the test that hangs."],
    'stopped: $reason; no pull request was opened': ["stopped: the acceptance criteria changed after your pick; no pull request was opened"],
    'stopped: $why; no pull request was opened': ["stopped: the intent check found a line not met: x; no pull request was opened",
                                                  "stopped: the intent check's answer could not be read, so it counts as not met; no pull request was opened"],
    'held: $why': ["held: unknown: nothing filed: x"],  # file_memo.py prints "unknown: ..." when it cannot file
    'safety stop: $f $why': ["safety stop: CHANGELOG.md holds a private name"],
    'paused: $1; the next run picks up the built change at review, without planning again': [],  # short() itself; its callers are scanned
    'stopped: $1': [],
    'stopped: $SPEND_WHY': ["stopped: over the $2.00 cap at source x, 2.1000",
                            "stopped: the call's cost could not be read at source x, so its spend is unknown; the total so far, $0.0600, is kept"],  # daily_loop.sh: spend()
    '$SPEND_WHY': ["over the $2.00 cap at the engineer, 2.1000",
                   "the call's cost could not be read at the engineer, so its spend is unknown; the total so far, $0.0600, is kept"],
    '$STATE_MSG': ["state not saved: the record is committed in X but not pushed; run: git -C X pull --rebase"],
    '$why; the message is at $out': ["unknown: nothing filed: x; the message is at y"],
}


def string_end(s, i):
    """s[i] opens a double-quoted shell string; the index just past its closing quote, honouring $( ) nesting."""
    j, depth = i + 1, 0
    while j < len(s):
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if c == "$" and s[j + 1:j + 2] == "(":
            depth, j = depth + 1, j + 2
            continue
        if depth and c == ")":
            depth -= 1
        elif depth and c == '"':
            j = string_end(s, j)
            continue
        elif not depth and c == '"':
            return j + 1
        j += 1
    raise ValueError("unterminated string")


def sample(template):
    """The words a template prints, with each expansion ($x, ${x}, $(..)) replaced by X."""
    if template in SAMPLES:
        return SAMPLES[template]
    out, i = "", 0
    while i < len(template):
        c = template[i]
        if c == "\\" and i + 1 < len(template):
            out, i = out + template[i + 1], i + 2
        elif c == "$" and template[i + 1:i + 2] == "(":
            depth, i = 1, i + 2
            while depth and i < len(template):
                depth += (template[i] == "(") - (template[i] == ")")
                i += 1
            out += "X"
        elif c == "$" and template[i + 1:i + 2] == "{":
            i = template.index("}", i) + 1
            out += "X"
        elif c == "$" and re.match(r"[A-Za-z_0-9]", template[i + 1:i + 2]):
            m = re.compile(r"\w+").match(template, i + 1)
            i = m.end()
            out += "X"
        else:
            out, i = out + c, i + 1
    return [out]


def sites(path):
    """(kind, template, trailing, line) for every stop, log, short, echo-then-exit and done= in a script."""
    text = path.read_text()
    found = []
    for m in re.finditer(r'(?<![\w-])(stop|log|short|echo)\s+"|(?<![\w-])(done)="', text):
        kind = m[1] or m[2]
        q = m.end() - 1
        end = string_end(text, q)
        template = text[q + 1:end - 1]
        tail = text[end:end + 40]
        found.append((kind, template, tail, text.count("\n", 0, q) + 1))
    return found


def outcomes(path):
    """(line, kind, outcome sample, exit code that follows an echo, or None) for each place a script ends or records a run."""
    out, skipped = [], []
    for kind, template, tail, line in sites(path):
        if kind == "echo":
            m = re.match(r";\s*exit (\d+)", tail)
            if not m:
                continue  # an echo that does not end the run is not an outcome
            code = int(m[1])
        else:
            code = None
        if template.startswith("$") and template not in SAMPLES:
            skipped.append((line, kind, template))  # log "$1" in stop() itself, and the like
            continue
        for words in sample(template):
            if kind == "short":  # short() ends the run as paused when a change was built, stopped when not
                out += [(line, kind, f"paused: {words}; the next run picks up the built change at review, without planning again", None),
                        (line, kind, f"stopped: {words}", None)]
            else:
                out.append((line, kind, words, code))
    return out, skipped


FILES = (KIT / "scripts/daily_loop.sh", KIT / "scripts/run.sh")


def all_outcomes():
    rows = []
    for f in FILES:
        o, _ = outcomes(f)
        rows += [(f.name, *r) for r in o]
    # The kit's own refusal, printed by tamper.py and exited on by daily_loop.sh before anything else.
    rows.append(("tamper.py", 0, "message", tamper.message(["scripts/x.py"]), None))
    return rows


class Table(unittest.TestCase):
    def test_every_outcome_maps_to_exactly_one_row(self):
        rows = all_outcomes()
        self.assertGreater(len(rows), 90, "the scan found too few outcomes to be reading the scripts")
        for name, line, kind, outcome, _ in rows:
            hits = [r[0] for r in loop_lib.GATES if re.match(r[0], outcome)]
            legacy = [r[0] for r in loop_lib.LEGACY if re.match(r[0], outcome)]
            self.assertEqual(legacy, [], f"{name}:{line} {outcome!r} matches a legacy row, which would hide its real row")
            self.assertEqual(len(hits), 1, f"{name}:{line} {kind} {outcome!r} matches {len(hits)} rows: {hits}")

    def test_the_scan_sees_the_known_sites(self):
        seen = {o for _, _, _, o, _ in all_outcomes()}
        for expected in ("stopped: the tests fail on X before any change", "safety stop: the change edits the profile",
                         "held for the owner: X"):
            self.assertTrue(any(o.startswith(expected) for o in seen), expected)

    def test_no_stop_names_its_own_exit_code(self):
        # stop() reads the code from the table, so a number at a call site could only disagree with it.
        for f in FILES:
            for kind, template, tail, line in sites(f):
                if kind == "stop":
                    self.assertFalse(re.match(r"\s+\d\b", tail), f"{f.name}:{line} stop {template!r} passes an exit code")

    def test_echo_and_exit_sites_use_the_table_code(self):
        checked = 0
        for name, line, kind, outcome, code in all_outcomes():
            if code is not None:
                self.assertEqual(code, loop_lib.GATE_EXIT[loop_lib.gate_state(outcome)], f"{name}:{line} {outcome!r}")
                checked += 1
        self.assertGreater(checked, 12)

    def test_tamper_exit_and_run_sh_not_filed_use_the_table_code(self):
        self.assertEqual(loop_lib.gate_state(tamper.message(["x"])), "safety_stop")
        self.assertRegex((KIT / "scripts/daily_loop.sh").read_text(), r'tamper\.py" check "\$KIT"\) \|\| \{ echo "\$why"; exit 5; \}')
        self.assertEqual(loop_lib.GATE_EXIT["safety_stop"], 5)
        run_sh = (KIT / "scripts/run.sh").read_text()
        code = loop_lib.GATE_EXIT[loop_lib.gate_state("weekly review not filed, x")]
        self.assertRegex(run_sh, r'\*"not filed"\*\) .*; exit ' + str(code) + r' ;; esac')

    def test_exit_codes_follow_the_state_and_avoid_taken_numbers(self):
        self.assertEqual(set(loop_lib.GATE_EXIT), STATES)
        codes = list(loop_lib.GATE_EXIT.values())
        self.assertEqual(loop_lib.GATE_EXIT["waiting_for_decision"], 0)  # the owner chose 0: an open pull request is not a red day
        self.assertEqual(len(set(codes)), len(codes) - 1)  # waiting shares 0 with pass; the rest are distinct
        self.assertEqual(loop_lib.GATE_EXIT["pass"], 0)
        self.assertFalse({2, 124, 143} & set(codes))
        for pat, state, label, nxt, offer in loop_lib.GATES:
            self.assertIn(state, STATES)
            self.assertIn(offer, ("", "allow", "resume"))
            self.assertTrue(label)
            self.assertTrue(nxt or state == "pass", pat)  # every stop that is not a pass says what to do next

    def test_only_a_held_question_offers_allow(self):
        allowing = [r[0] for r in loop_lib.GATES if r[4] == "allow"]
        self.assertEqual(allowing, ["held for the owner:"])
        for words in ("safety stop: the change edits the profile", "blocked: design: x", "stopped: tests fail on the branch"):
            self.assertNotEqual(loop_lib.gate(words)["offer"], "allow")

    def test_the_table_is_what_the_state_and_label_come_from(self):
        self.assertEqual(loop_lib.gate_state("something no row knows"), "failed")  # a new stop is never read as a pass
        self.assertEqual(stats.label("something no row knows"), stats.UNKNOWN)
        self.assertEqual(stats.label("paused: too little budget left to build and review today; the next run builds X first"), "paused to stay within budget")
        self.assertEqual(stats.label("paused: the last two changes were closed unmerged; the owner needs to look"), "paused after two closed changes")


class Words(unittest.TestCase):
    """The words that used to cover several states now keep to one each."""

    def test_safety_stops_are_never_a_hold(self):
        for words in ("safety stop: the canary token was written out during the build; read X before running again",
                      "safety stop: the change holds a secret; nothing was pushed",
                      "safety stop: the pull request text holds a token; nothing was pushed",
                      "safety stop: the change edits the profile"):
            self.assertEqual(loop_lib.gate_state(words), "safety_stop")
            self.assertFalse(words.startswith("held"))
        # Lines older kits wrote still read as what they were.
        self.assertEqual(loop_lib.gate_state("held: the canary token was written out during the build; read X"), "safety_stop")
        self.assertEqual(loop_lib.gate_state("held for the owner: the change holds a secret; nothing was pushed"), "safety_stop")
        self.assertEqual(loop_lib.gate_state("held for the owner: the code is on the stop list: deletion: code.py"), "waiting_for_decision")

    def test_blocked_with_no_question_does_not_claim_one(self):
        out = loop_lib.morning(MEMO_NO_QUESTION, "blocked: the engineer needs x", "2026-11-03", "/kit", "")
        self.assertNotIn("asked you the question below", out)
        self.assertIn("left no question", out)
        asked = loop_lib.morning(MEMO_NO_QUESTION, "blocked: the engineer needs x", "2026-11-03", "/kit", "",
                                 ask="Owner question:\nWhat does it need? Recommended: say.\n\nQuestion bet: B\n")
        self.assertIn("asked you the question below", asked)

    def test_the_brief_offers_allow_only_for_a_real_question_about_a_bet(self):
        ask = "Owner question:\nLet it through? Recommended: yes.\n\nQuestion bet: Bet A\n"
        held = loop_lib.morning(MEMO_NO_QUESTION, "held for the owner: it is on the stop list", "2026-11-03", "/kit", "", ask=ask)
        self.assertIn("decide.py allow", held)
        for outcome in ("held for the owner: it is on the stop list", "safety stop: the change edits the profile"):
            self.assertNotIn("decide.py allow", loop_lib.morning(MEMO_NO_QUESTION, outcome, "2026-11-03", "/kit", ""), outcome)
        stop = loop_lib.morning(MEMO_NO_QUESTION, "safety stop: the change edits the profile", "2026-11-03", "/kit", "", ask=ask)
        self.assertNotIn("decide.py allow", stop)
        self.assertNotIn("question below", stop)


MEMO_NO_QUESTION = "Recommendation:\nnone\n"


class Fixture(unittest.TestCase):
    def setUp(self):
        self.d = pathlib.Path(scratch.mkdtemp())
        self.ctx = self.d / "ctx"; self.ctx.mkdir()
        self.profile = self.d / "profile.md"
        self.profile.write_text("**Product:** Demo\n**Context path:** ctx\n")
        (self.ctx / "team-log.md").write_text("# Team log\n")
        self.cwd = os.getcwd()
        os.chdir(self.d)

    def tearDown(self):
        os.chdir(self.cwd)

    def log(self, day, outcome):
        with open(self.ctx / "team-log.md", "a") as f:
            f.write(f"- {day} | {outcome} | $0.10\n")

    def decide(self, *args):
        r = subprocess.run([sys.executable, str(KIT / "scripts/decide.py"), *args], cwd=self.d, capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr


class Allow(Fixture):
    def brief(self, **kw):
        (self.ctx / "options.json").write_text(json.dumps({"date": "2026-11-03", "options": [], "question": "Let it through?", "bet": "Bet A", **kw}))

    def test_allow_is_refused_after_a_safety_stop(self):
        self.brief()
        self.log("2026-11-03", "safety stop: the change edits the profile")
        code, out = self.decide("allow")
        self.assertEqual(code, 4)
        self.assertIn("safety stop", out)
        self.assertIn("Nothing to allow", out)
        self.assertFalse((self.ctx / "allowed.md").exists(), "a refused allow must write nothing")
        code, out = self.decide("allow", "Bet A")  # naming the bet does not get round it
        self.assertEqual(code, 4)
        self.assertFalse((self.ctx / "allowed.md").exists())

    def test_allow_still_works_for_a_real_hold(self):
        self.brief()
        self.log("2026-11-03", "held for the owner: the code is on the stop list: deletion: code.py")
        code, out = self.decide("allow")
        self.assertEqual(code, 0, out)
        self.assertIn("allowed by owner", (self.ctx / "allowed.md").read_text())

    def test_allow_with_no_question_and_no_bet_names_nothing(self):
        (self.ctx / "options.json").write_text(json.dumps({"date": "2026-11-03", "options": [], "question": "", "bet": ""}))
        self.log("2026-11-03", "held for the owner: x")
        code, out = self.decide("allow")
        self.assertEqual(code, 2)
        self.assertFalse((self.ctx / "allowed.md").exists())


class Status(Fixture):
    def status(self):
        r = subprocess.run([sys.executable, str(KIT / "scripts/status.py")], cwd=self.d, capture_output=True, text=True,
                           env=dict(os.environ, GH_BIN="/usr/bin/true"))
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def test_a_run_that_did_not_pass_is_not_idle(self):
        cases = {
            "stopped: could not fetch main": ("failed", "refused a step"),
            "stopped: the working tree has changes (x), so nothing was built.": ("blocked", "not committed"),
            "safety stop: the change edits the profile": ("safety_stop", "nothing to allow"),
            "waiting: GitHub. To build \"T\", add a GitHub repo": ("waiting_for_decision", "Add a GitHub repo"),
            "paused: the last two changes were closed unmerged; the owner needs to look": ("waiting_for_decision", "decide resume"),
        }
        for outcome, (state, words) in cases.items():
            (self.ctx / "team-log.md").write_text("# Team log\n")
            self.log("2026-11-03", outcome)
            out = self.status()
            self.assertIn(f"state: {state}\n", out, outcome)
            self.assertIn(words, out, outcome)
            self.assertIn(outcome[:30], out)

    def test_a_pass_after_the_stop_is_idle_again(self):
        self.log("2026-11-03", "stopped: could not fetch main")
        self.log("2026-11-04", "quiet: nothing fired, x")
        self.assertIn("state: idle", self.status())

    def test_the_owners_call_clears_a_waiting_state(self):
        self.log("2026-11-03", "held for the owner: x")
        self.assertIn("state: waiting_for_decision", self.status())
        (self.ctx / "allowed.md").write_text("- 2026-11-03 | Bet A | allowed by owner\n")
        self.assertIn("state: idle", self.status())


class Event(Fixture):
    def test_the_run_event_carries_gate_state_and_keeps_its_old_fields(self):
        ev = handoff.event(str(self.profile), "safety stop: the change edits the profile")
        self.assertEqual(ev["gate_state"], "safety_stop")
        self.assertEqual(ev["kind"], "safety stop")
        self.assertEqual(ev["schema"], "dualtrack.run.v1")
        for old in ("time", "product", "goal", "outcome", "kind", "pull_request", "options", "question", "confirmed_bet", "steer", "weekly", "safety_checks"):
            self.assertIn(old, ev)
        self.assertEqual(handoff.event(str(self.profile), "unknown: could not read pull requests")["kind"], "unknown")
        self.assertEqual(handoff.event(str(self.profile), "unknown: could not read pull requests")["gate_state"], "failed")
        self.assertEqual(handoff.event(str(self.profile), "opened: T, https://github.com/o/r/pull/1, x")["gate_state"], "pass")

    def test_every_kind_the_docs_list_is_a_kind_the_table_can_produce(self):
        doc = (KIT / "docs/handoff.md").read_text()
        for kind in ("unknown", "safety stop", "ready", "already built"):
            self.assertIn(f"`{kind}`", doc)
        for state in STATES:
            self.assertIn(f"`{state}`", doc)


class Dashboard(Fixture):
    def render(self, **kw):
        return dashboard.render(str(self.ctx), "2026-11-04", "/kit", "none", str(self.profile), **kw)

    def test_the_strip_names_the_last_run_state(self):
        self.log("2026-11-03", "stopped: the tests fail on X before any change")
        page = self.render()
        self.assertIn('id="last-run"', page)
        self.assertIn("Blocked", page)
        self.assertIn("Fix them on your main branch", page)

    def test_allow_card_only_with_a_real_question_and_never_after_a_safety_stop(self):
        (self.ctx / "options.json").write_text(json.dumps({"date": "2026-11-03", "options": [], "question": "Let it through?", "bet": "Bet A"}))
        self.log("2026-11-03", "held for the owner: it is on the stop list")
        self.assertIn('data-kind="allow"', self.render())
        (self.ctx / "options.json").write_text(json.dumps({"date": "2026-11-03", "options": [], "question": "", "bet": ""}))
        self.assertNotIn('data-kind="allow"', self.render())
        (self.ctx / "options.json").write_text(json.dumps({"date": "2026-11-03", "options": [], "question": "Let it through?", "bet": "Bet A"}))
        self.log("2026-11-04", "safety stop: the change edits the profile")
        page = self.render()
        self.assertNotIn('data-kind="allow"', page)
        self.assertIn("Safety stop", page)

    def test_resume_card_after_two_closed_changes(self):
        self.log("2026-11-03", "paused: the last two changes were closed unmerged; the owner needs to look")
        self.assertIn('data-kind="resume"', self.render())

    def test_the_server_takes_allow_and_resume_with_no_text_and_nothing_else_new(self):
        self.assertTrue(dashboard_server.allowed(["allow"]))
        self.assertTrue(dashboard_server.allowed(["resume"]))
        self.assertFalse(dashboard_server.allowed(["allow", "Another bet"]))
        self.assertFalse(dashboard_server.allowed(["resume", "x"]))
        self.assertFalse(dashboard_server.allowed(["areas"]))


class Weekly(unittest.TestCase):
    def test_stats_split_the_two_pauses_and_have_no_catch_all(self):
        log = "".join(f"- 2026-11-0{i} | {o} | $0.1\n" for i, o in enumerate([
            "paused: the last two changes were closed unmerged; the owner needs to look",
            "paused: too little budget left to build and review today; the next run builds X first",
            "stopped: could not fetch main", "safety stop: the change edits the profile", "never heard of this"], 1))
        kinds = stats.stats(log, "")["kinds"]
        self.assertEqual(kinds["paused after two closed changes"], 1)
        self.assertEqual(kinds["paused to stay within budget"], 1)
        self.assertEqual(kinds["stopped by a safety check"], 1)
        self.assertEqual(kinds[stats.UNKNOWN], 1)
        self.assertNotIn("stopped on an error", kinds)


if __name__ == "__main__":
    unittest.main()
