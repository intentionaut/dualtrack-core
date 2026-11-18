#!/usr/bin/env python3
import os
"""File a product manager message into the record. Stdlib only.

Usage: python3 scripts/file_memo.py <profile.md> <message.md>
Exit 0 when filed. Exit 2 and print a line starting `unknown:` when not.
With CHECK_ONLY set, it checks and writes nothing.
"""
import pathlib
import re
import profile_value  # noqa: E402
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import loop_lib  # noqa: E402

STATUS = re.compile(
    r"^Product manager (?:(memo), (\d{4}-\d{2}-\d{2}): (ok|gaps|unknown)"
    r"|(daily), (\d{4}-\d{2}-\d{2}): (quiet|changed|unknown))\s*$"
)
MOVES = ("Fix", "Reach", "Capture", "Offer", "Distribute", "Compound", "Prove", "Learn")
RECORD = re.compile(r"^- (decisions|bets|evidence|gaps): (.+)$")


def field(profile, name):
    return profile_value.field(profile, name)


def unique(folder, stem, suffix=".md"):
    """Open a new file; a second run the same day gets -2, -3, and so on."""
    for n in range(1, 1000):
        path = folder / f"{stem}{'' if n == 1 else f'-{n}'}{suffix}"
        try:
            return path, path.open("x")
        except FileExistsError:
            continue
    raise OSError(f"no free name for {stem}")


MODES = ("acquisition", "activation", "optimisation")


def check_mode(text, profile):
    """The profile may run up to 2 modes at once; each memo works in one of them."""
    listed = [m for m in MODES if re.search(rf"\b{m}\b", field(profile, "Mode"))]
    if not listed:
        return
    if len(listed) > 2:
        raise ValueError("the profile lists more than 2 modes; run at most 2 modes at once")
    memo = re.search(r"^Mode: (\w+)", text, re.M)
    if not memo or memo[1] not in listed:
        raise ValueError(f"the memo's Mode is not one of the profile's modes ({', '.join(listed)})")


def owner_confirmed(text, bets):
    """The owner's call beats the score: the top pick is a bet the owner confirmed in the record."""
    title = re.search(r"^Recommendation:\s*\n(.+)$", text, re.M)
    pick = title[1].strip().lower().rstrip(".") if title else ""
    # The memo often quotes only the bet's first sentence, so a prefix that ends at a full stop counts.
    return bool(pick) and any(t.strip().lower() == pick or t.strip().lower().startswith(pick + ".")
                              for t in loop_lib.open_titles(bets))


def check_move(text, decisions, bets=""):
    """Return the memo's move. Learn cannot win two runs in a row."""
    m = re.search(r"^Move: (\w+)\s*$", text, re.M)
    if not m or m[1] not in MOVES:
        raise ValueError("the memo names no valid Move")
    if not re.search(r"^- decisions: ", text, re.M):
        raise ValueError("the memo has no decisions line")
    score = re.search(r"^Score: .*\bgoal link ([1-5])\b", text, re.M)
    if not score:
        raise ValueError("the Score has no goal link from 1 to 5")
    if int(score[1]) < 3 and not os.environ.get("CONFIRMED_BET") and not owner_confirmed(text, bets):  # the owner may overrule the score
        raise ValueError("a goal link below 3 cannot be the top pick")
    if not re.search(r"^Goal link: \S", text, re.M):
        raise ValueError("the memo does not spell out its Goal link")
    if not re.search(r"^Moves: .*[A-Za-z]", text, re.M):
        raise ValueError("Moves must name a number, not a digit")
    verdict = re.search(r"^Verdict: (confirmed|needs_validation|rejected)\b.*$", text, re.M)
    if not verdict:
        raise ValueError("the memo has no Verdict")
    if verdict[1] == "rejected":
        raise ValueError("a rejected candidate cannot be the top pick")
    # The fact may sit in Why, or on the Verdict line itself ("Verdict: needs_validation. <fact>"); a bare verdict still fails.
    if verdict[1] == "needs_validation" and not re.search(r"^Why: .*needs_validation", text, re.M) \
            and not re.match(r"needs_validation\s*[.:;,-]\s*\S+(?:\s+\S+){3,}", verdict[0][len("Verdict: "):]):
        raise ValueError("Why must state the needs_validation fact")
    title = re.search(r"^Recommendation:\s*\n(.+)$", text, re.M)
    if title and re.search(rf"^- (?:\d{{4}}-\d{{2}}-\d{{2}} \| )?(?:decisions: )?{re.escape(title[1].strip())} \| rejected:",
                           decisions + "\n" + text, re.M | re.I):
        raise ValueError("this candidate was already rejected")
    if m[1] == "Learn" and not re.search(r"^Why: .*no reversible bet", text, re.M | re.I):
        raise ValueError("Learn cannot be the top pick while a reversible bet exists")
    last = re.findall(r"\| move: (\w+)", decisions)
    if m[1] == "Learn" and last and last[-1] == "Learn":
        raise ValueError("Learn cannot win two runs in a row")
    return m[1]


def check_new_ideas(text, profile):
    """A weekly memo must carry as many new ideas as the profile's New idea slots."""
    slots = int(field(profile, "New idea slots") or 1)
    section = re.search(r"^New ideas:\n((?:- .+\n?)*)", text, re.M)
    found = len(section.group(1).strip().splitlines()) if section else 0
    if found < slots:
        raise ValueError(f"the memo has {found} new ideas, and the profile asks for {slots}")


def check_new_idea_bet(text, profile, bets):
    """A reserved slot: with none proposed or running, the memo must propose a new idea."""
    if int(field(profile, "New idea slots") or 1) < 1 or "new idea" in bets.lower():
        return
    section = re.search(r"^Bets:\n((?:- .+\n?)*)", text, re.M)
    if not section or "new idea" not in section.group(1).lower():
        raise ValueError("the Bets must include a new idea")


def file_memo(profile_path, message_path):
    profile = pathlib.Path(profile_path).read_text()
    text = pathlib.Path(message_path).read_text()
    start = re.search(r"^Product manager (?:memo|daily), ", text, re.M)
    text = text[start.start():] if start else text  # agents sometimes narrate a line first; the memo starts at its status line
    m = STATUS.match(text.split("\n", 1)[0])
    if not m:
        raise ValueError("the first line is not a status line")
    kind, date, status = m.group(1, 2, 3) if m.group(1) else m.group(4, 5, 6)
    cadence = "weekly" if kind == "memo" else "daily"
    store = field(profile, "Context store")
    if store not in ("local", "obsidian", "notion"):
        raise ValueError(f"Context store is {store or 'missing'}")
    if not field(profile, "Context path"):
        raise ValueError("Context path is missing")
    base = pathlib.Path.cwd()  # relative paths are relative to the product repo, where every script runs
    root = base / field(profile, "Context path")
    decisions = root / "decisions.md"
    move = None
    if kind == "memo":
        bets = root / "bets.md"
        check_mode(text, profile)
        move = check_move(text, decisions.read_text() if decisions.is_file() else "", bets.read_text() if bets.is_file() else "")
        check_new_ideas(text, profile)
        try:
            check_new_idea_bet(text, profile, bets.read_text() if bets.is_file() else "")
            slot = ""
        except ValueError:
            slot = "no new-idea bet this run, so the reserved slot stays open"  # a gap, not a refusal: it blocked 2 of 3 real runs
    record = text.split("Record:", 1)[1] if "Record:" in text else ""
    if re.search(r"confirmed by owner", record, re.I):
        raise ValueError("the memo claims an owner confirmation; only the owner confirms a bet, with decide.py")
    if os.environ.get("CHECK_ONLY"):
        return None, store
    (root / "memos").mkdir(parents=True, exist_ok=True)
    (root / "numbers").mkdir(exist_ok=True)

    path, out = unique(root / "memos", f"{date}-{cadence}")
    with out:
        if store == "obsidian":
            out.write(f"---\ndate: {date}\ncadence: {cadence}\nstatus: {status}\n---\n\n")
        out.write(text.rstrip() + "\n")
        if store == "obsidian":
            out.write("\n[[decisions]] [[bets]] [[evidence]] [[gaps]]\n")

    link = f"[[memos/{path.stem}]]" if store == "obsidian" else f"memos/{path.name}"
    for line in text.split("Record:", 1)[1].splitlines() if "Record:" in text else []:
        entry = RECORD.match(line.strip())
        if entry:
            with (root / f"{entry[1]}.md").open("a") as f:
                tag = f" | move: {move}" if entry[1] == "decisions" and move and "| rejected:" not in entry[2] else ""
                f.write(f"- {date} | {entry[2]}{tag} | {link}\n")

    if kind == "memo" and slot:
        with (root / "gaps.md").open("a") as f:
            f.write(f"- {date} | {slot} | {link}\n")

    numbers = base / field(profile, "Numbers file")
    snapshot = root / "numbers" / f"{date}.md"
    if numbers.is_file() and not snapshot.exists():
        shutil.copyfile(numbers, snapshot)
    return path, store


def main():
    if len(sys.argv) != 3:
        print("unknown: usage: file_memo.py <profile.md> <message.md>")
        return 2
    try:
        path, store = file_memo(sys.argv[1], sys.argv[2])
    except (OSError, ValueError) as e:
        print(f"unknown: nothing filed: {e}")
        return 2
    print("checked: it would file" if path is None else f"filed: {path}")
    if store == "notion":
        print("notion: pending, run prompts/notion-sync.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
