"""The owner's dashboard: one page from the record, with no model call."""
import html.parser
import json
import pathlib
import re
import subprocess
import sys
import unittest

KIT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "scripts"))
import dashboard
try:
    import scratch
except ImportError:  # run as tests.test_x from the repo root
    from tests import scratch


class Dashboard(unittest.TestCase):
    def setUp(self):
        self.c = pathlib.Path(scratch.mkdtemp())
        (self.c / "options.json").write_text(json.dumps({"date": "2026-11-09", "table": "ab12", "question": "", "options": [
            {"change": "Reorder <button>", "reason": "repeat orders", "expected": "up 10%"}]}))
        (self.c / "team-log.md").write_text("- 2026-10-31 | quiet | $1.00\n- 2026-11-08 | stopped: tests failed | $0.50\n"
                                            "- 2026-11-09 | opened: #7 | $3.00\n")
        (self.c / "bets.md").write_text(
            "- 2026-11-01 | Fix it | expected: fewer errors | read by 2026-11-08 | kill: none | baseline: 40 a week\n"
            "- 2026-11-01 | Fix it | started: https://github.com/o/r/pull/7\n")
        (self.c / "decisions.md").write_text("- 2026-11-02 | #7 fix | yes: merged\n")

    def test_the_page_puts_what_needs_the_owner_first(self):
        page = dashboard.render(str(self.c), "2026-11-09", "/kit", "none", str(self.profile()))
        self.assertLess(page.index('id="needs-you"'), page.index('id="outcomes"'))
        self.assertLess(page.index('id="outcomes"'), page.index('id="cost"'))
        self.assertIn('id="ask-count">2</span>', page)  # the pick and the overdue result
        self.assertIn('data-kind="pick" data-cmd="python3 /kit/scripts/decide.py" data-table="ab12"', page)
        self.assertIn('data-kind="result" data-cmd="python3 /kit/scripts/decide.py" data-title="Fix it"', page)
        self.assertIn("Did <em>Fix it</em> help?", page)
        self.assertIn("40 a week", page)

    def test_every_inbox_status_has_a_place_on_the_board(self):
        import loop_lib
        self.assertEqual(set(loop_lib.BOARD), set(loop_lib.INBOX_NEXT))  # a new status must be placed or ruled off

    def test_the_board_shows_each_bet_by_stage_with_who_signed_it(self):
        import loop_lib
        with open(self.c / "bets.md", "a") as f:
            f.write("- 2026-11-03 | Shorter <install> | confirmed by owner | Bug, P1 | area: Onboarding | by: Ana\n"
                    "- 2026-11-03 | Guide the first run | confirmed by owner\n"
                    "- 2026-11-03 | Name the plans | confirmed by owner | by: Smith, Ana\n"
                    "- 2026-11-04 | Guide the first run | started: https://github.com/o/r/pull/8\n"
                    "- 2026-11-04 | Taken back | confirmed by owner | by: Ana\n"
                    "- 2026-11-04 | Taken back | withdrawn: owner took back this pick | by: Ana\n")
        cols = loop_lib.board(str(self.c))
        where = {c["title"]: (col, c["owner"]) for col, cards in cols.items() for c in cards}
        self.assertEqual(where["Shorter <install>"], ("Picked", "Ana"))
        self.assertEqual(next(c["area"] for c in cols["Picked"] if c["title"] == "Shorter <install>"), "Onboarding")
        self.assertEqual(where["Guide the first run"], ("Building", "the owner"))  # signed before names were kept
        self.assertEqual(where["Fix it"], ("Shipped, waiting for evidence", "Dualtrack agents"))
        self.assertEqual(next(c["kind"] for c in cols["Picked"] if c["title"] == "Name the plans"), "")  # a comma in a name is not a type
        self.assertNotIn("Taken back", where)
        self.assertNotIn("Reorder <button>", where)  # offered, not yet a bet
        page = dashboard.render(str(self.c), "2026-11-09", "/kit", "none", str(self.profile()))
        self.assertLess(page.index('id="needs-you"'), page.index('id="bets"'))
        self.assertIn("<h4>Shorter &lt;install&gt;</h4>", page)
        self.assertIn('<div class=tags><span class="tag area">Onboarding</span><span class="tag">Bug, P1</span></div>', page)
        self.assertIn("Owner <strong class=agents>Dualtrack agents</strong>", page)
        self.assertIn('<form class="act owner" data-kind="owner" data-cmd="python3 /kit/scripts/decide.py" data-title="Shorter &lt;install&gt;">', page)

    def profile(self, extra=""):
        p = self.c / "profile.md"
        p.write_text("**Product:** Shop, a bakery's online orders\n\n**Goal:** more repeat orders\n\n**Mode:** activation\n\n" + extra)
        return p

    def test_the_page_never_looks_like_a_secret_to_the_loops_scanner(self):
        import loop_lib  # the loop holds the whole record when any file in it looks secret-shaped
        self.assertEqual(loop_lib.leaks(dashboard.render(str(self.c), "2026-11-09", "/kit", "none", str(self.profile()))), [])

    def test_the_words_come_from_the_profile_not_the_code(self):
        page = dashboard.render(str(self.c), "2026-11-09", "", "", str(self.profile()))
        self.assertIn("DUALTRACK · SHOP", page)
        self.assertIn("Goal: more repeat orders.", page)
        self.assertIn("Working on activation", page)
        self.assertIn("Pick the next change", page)
        self.assertNotIn("this week&#39;s change", page)

    def test_before_launch_the_page_leads_with_delivery_not_unknowns(self):
        page = dashboard.render(str(self.c), "2026-11-09", "", "", str(self.profile("**Launched:** no\n")))
        self.assertIn("No users yet", page)
        self.assertLess(page.index('id="cost"'), page.index('id="outcomes"'))
        self.assertNotIn("Result due", page)

    def test_record_text_is_escaped_never_run(self):
        page = dashboard.render(str(self.c), "2026-11-09")
        self.assertIn("Reorder &lt;button&gt;", page)
        self.assertNotIn("Reorder <button>", page)

    def test_cost_is_counted_from_the_record(self):
        page = dashboard.render(str(self.c), "2026-11-09", cap="5")
        self.assertIn("$3.50 over 2 runs; the week before, $1.00", page)
        self.assertIn("Run cap <b>$5.00</b>", page)
        self.assertIn("stopped: tests failed", page)

    def test_an_empty_record_still_makes_a_page(self):
        page = dashboard.render(scratch.mkdtemp(), "2026-11-09")
        self.assertIn("Your product operating system", page)
        self.assertNotIn('id="needs-you"', page)

    def test_the_command_writes_the_page_into_the_record(self):
        r = subprocess.run([sys.executable, str(KIT / "scripts/dashboard.py"), str(self.c), "2026-11-09"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.c / "dashboard.html").read_text().startswith("<!doctype html>"))


def _lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _rgb(h):
    h = h.lstrip("#")
    h = "".join(c * 2 for c in h) if len(h) == 3 else h[:6]
    return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]


def _oklab(h):
    r, g, b = map(_lin, _rgb(h))
    l, m, s = (x ** (1 / 3) for x in (0.41222147 * r + 0.53633253 * g + 0.05144599 * b,
                                      0.21190349 * r + 0.68069954 * g + 0.10739695 * b,
                                      0.08830246 * r + 0.28171883 * g + 0.62997870 * b))
    return [0.21045425 * l + 0.79361778 * m - 0.00407204 * s,
            1.97799849 * l - 2.42859220 * m + 0.45059370 * s,
            0.02590403 * l + 0.78277176 * m - 0.80867576 * s]


def _hex(lab):
    L, a, b = lab
    l, m, s = (x ** 3 for x in (L + 0.39633777 * a + 0.21580375 * b, L - 0.10556134 * a - 0.06385417 * b,
                                L - 0.08948417 * a - 1.29148554 * b))
    rgb = (4.07674166 * l - 3.30771159 * m + 0.23096992 * s, -1.26843800 * l + 2.60975740 * m - 0.34131939 * s,
           -0.00419608 * l - 0.70341861 * m + 1.70761470 * s)
    return "#" + "".join(f"{round(min(1, max(0, c)) * 255):02x}" for c in rgb)


def _contrast(a, b):
    y = lambda h: sum(w * _lin(c) for w, c in zip((0.2126, 0.7152, 0.0722), _rgb(h)))
    hi, lo = sorted((y(a), y(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


class Contrast(unittest.TestCase):
    """Reads dashboard.css itself: the colours a rule really uses, in both themes, never a copy of them."""
    CSS = (KIT / "scripts/dashboard.css").read_text()

    def tokens(self, dark):
        t = {}
        for sel, body in re.findall(r"(?m)^([^{}@\n]+)\{([^{}]*)\}", self.CSS):
            if sel.strip() == ":root" or (dark and sel.strip() == ":root.dark"):
                t.update(re.findall(r"(--[\w-]+):\s*([^;]+)", body))
        return t

    def colour(self, v, t):
        v = v.strip()
        m = re.fullmatch(r"var\((--[\w-]+)\)", v)
        if m:
            return self.colour(t[m[1]], t)
        m = re.fullmatch(r"color-mix\(in oklab,\s*(.+?) (\d+)%,\s*(.+)\)", v)
        if m:
            a, b = _oklab(self.colour(m[1], t)), _oklab(self.colour(m[3], t))
            return _hex([x * int(m[2]) / 100 + y * (1 - int(m[2]) / 100) for x, y in zip(a, b)])
        return v

    def decl(self, sel, prop, dark, last=False):
        """The colour a rule sets for prop (last colour word of the value when last)."""
        body = ";".join(re.findall(r"(?:^|[}\s])" + re.escape(sel) + r"\{([^}]*)\}", self.CSS))
        m = re.search(r"(?:^|;)" + prop + r":([^;]+)", body)
        self.assertIsNotNone(m, f"{sel} sets no {prop}")
        v = m[1].strip()
        if last:
            v = re.findall(r"var\([^)]*\)|#\w+", v)[-1]
        return self.colour(v, self.tokens(dark))

    def test_text_and_state_colours_meet_aa_in_both_themes(self):
        for dark in (False, True):
            t, c = self.tokens(dark), lambda n: self.colour(f"var(--{n})", self.tokens(dark))
            for fg, bg, need in [("text", "page", 4.5), ("text", "card", 4.5), ("muted-text", "page", 4.5), ("muted-text", "card", 4.5),
                                 ("muted-text", "surface", 4.5), ("good", "page", 4.5), ("good", "card", 4.5), ("good", "good-bg", 4.5),
                                 ("ask", "page", 4.5), ("ask", "card", 4.5), ("ask", "ask-bg", 4.5),
                                 ("ring", "card", 3.0), ("color-accent-500", "card", 3.0), ("color-primary-500", "card", 3.0)]:
                with self.subTest(theme="dark" if dark else "light", fg=fg, bg=bg):
                    self.assertGreaterEqual(_contrast(c(fg), c(bg)), need)

    def test_marks_and_controls_meet_non_text_contrast(self):
        for dark in (False, True):
            t = self.tokens(dark)
            card, page = self.colour("var(--card)", t), self.colour("var(--page)", t)
            for what, col, bg, need in [
                ("grey dot", self.decl(".st::before", "background", dark), card, 3.0),
                ("waiting ring", self.decl(".st.wait::before", "box-shadow", dark, True), card, 3.0),
                ("helped dot", self.decl(".st.helped::before", "background", dark), card, 3.0),
                ("late dot", self.decl(".st.late::before", "background", dark), card, 3.0),
                ("bar", self.decl(".bar", "fill", dark), card, 3.0),
                ("this week bar", self.decl(".bar.now", "fill", dark), card, 3.0),
                ("text field edge", self.decl("input[type=text]", "border", dark, True), page, 3.0),
                ("picked number", self.decl(".opt:has(input:checked) .opt-n", "background", dark), "#ffffff", 4.5),
                ("primary button", self.decl(".btn.primary", "background", dark), "#ffffff", 4.5),
                ("chosen segment", self.decl(".seg input:checked+span", "background", dark), "#ffffff", 4.5)]:
                with self.subTest(theme="dark" if dark else "light", what=what):
                    self.assertGreaterEqual(_contrast(col, bg), need)
            # this week's bar must differ from the others by lightness, not hue
            self.assertGreaterEqual(_contrast(self.decl(".bar", "fill", dark), self.decl(".bar.now", "fill", dark)), 1.5)

    def test_every_state_in_the_page_carries_words(self):
        outs = [{"status": s, "title": s, "expected": "x", "baseline": "y", "evidence": "", "day": "2026-11-01", "read_by": r}
                for s, r in [("Helped", ""), ("Did not help", ""), ("Unclear", ""), ("Evidence in", ""), ("Shipped, awaiting evidence", "2026-12-01"),
                             ("Shipped, awaiting evidence", "2026-11-01")]]
        page = dashboard.did_it_help(outs, "2026-11-09")[0] + dashboard.render(scratch.mkdtemp(), "2026-11-09")

        class Words(html.parser.HTMLParser):
            def __init__(s):
                super().__init__()
                s.stack, s.got = [], []

            def handle_starttag(s, tag, attrs):
                cls = set((dict(attrs).get("class") or "").split())
                s.stack.append([tag, bool(cls & {"st", "good", "ask", "agents", "count"}), ""])

            def handle_data(s, d):
                for f in s.stack:
                    f[2] += d

            def handle_endtag(s, tag):
                while s.stack:
                    f = s.stack.pop()
                    if f[1]:
                        s.got.append(f[2].strip())
                    if f[0] == tag:
                        break

        w = Words()
        w.feed(page)
        self.assertGreaterEqual(len(w.got), 6)
        for text in w.got:
            self.assertRegex(text, r"[A-Za-z0-9]", "a coloured state with no words")
        self.assertEqual(set(re.findall(r'class="st (\w+)"', page)), {"helped", "no", "wait", "late"})
        for cls in ("helped", "no", "wait", "late"):
            self.assertIn(f".st.{cls}", self.CSS)  # each state is styled, with its shape
        self.assertIn("rotate(45deg)", "".join(re.findall(r"\.st\.late::before\{[^}]*\}", self.CSS)))  # late is a diamond, not a second round dot


if __name__ == "__main__":
    unittest.main()
