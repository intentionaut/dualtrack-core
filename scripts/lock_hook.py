#!/usr/bin/env python3
"""PreToolUse guard for locked areas: denies the edit itself, before any file changes.

Claude Code sends the tool call as JSON on stdin. Exit 2 with the reason on stderr denies it; exit 0 lets it through.
It acts only inside a Dualtrack run, which names the profile in DUALTRACK_LOCK_PROFILE, the owner's allow record in
DUALTRACK_LOCK_ALLOWED and the bet in DUALTRACK_LOCK_BET. Outside a run it does nothing. Inside one it fails closed:
a profile it cannot read, input it cannot parse or any crash denies the call.
The matcher is safety_card.touched, the same one the post-build diff check uses.
"""
import json
import os
import re
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import safety_card  # noqa: E402

FILE_TOOLS = {"Edit": "file_path", "Write": "file_path", "MultiEdit": "file_path", "NotebookEdit": "notebook_path"}
ALL_ARGS = {"tee", "mv", "rm", "truncate", "touch", "unlink", "shred"}  # every file argument is written or removed
LAST_ARG = {"cp", "install", "ln"}  # only the destination is written
GIT_WRITES = {"checkout", "restore", "rm", "mv", "apply", "switch", "reset", "clean", "stash", "am"}


def rel(path, cwd):
    full = os.path.realpath(path if os.path.isabs(path) else os.path.join(cwd, path))
    root = os.path.realpath(cwd)
    return os.path.relpath(full, root) if full.startswith(root + os.sep) else path


def patch_files(path, cwd):
    """The files a patch file names, from its `+++ ` lines."""
    try:
        text = open(path if os.path.isabs(path) else os.path.join(cwd, path)).read()
    except OSError:
        return []
    return [re.sub(r"^[ab]/", "", m) for m in re.findall(r"^\+\+\+ (\S+)", text, re.M)]


def bash_targets(command, cwd):
    """Paths a command would write. shortcut: a plain reading of redirects and a short list of writing commands.
    It cannot see a write made by a script or interpreter (python -c, node, make), a shell variable, a glob or a
    directory-wide command (git checkout .). The tool hook for Edit and Write and the post-build revert cover those."""
    out = []
    for seg in re.split(r"&&|\|\||;|\||\n", command):
        try:
            words = shlex.split(seg)
        except ValueError:
            words = seg.split()
        out += [w.lstrip(">") for i, w in enumerate(words) if w.startswith(">") and w.lstrip(">")]
        out += [words[i + 1] for i, w in enumerate(words[:-1]) if re.fullmatch(r"\d*>>?", w)]
        words = [w for w in words if not w.startswith(">") and not re.fullmatch(r"\d*>>?", w)]
        while words and re.fullmatch(r"\w+=\S*", words[0]):
            words.pop(0)
        if not words:
            continue
        verb, args = os.path.basename(words[0]), [w for w in words[1:] if not w.startswith("-")]
        if verb == "sed" and any(re.fullmatch(r"-[a-zA-Z]*i\S*|--in-place\S*", w) for w in words[1:]):
            out += args[1:]  # the first non-flag argument is the script
        elif verb in ALL_ARGS:
            out += args
        elif verb in LAST_ARG and args:
            out.append(args[-1])
        elif verb == "git" and args and args[0] in GIT_WRITES:
            out += args[1:]
            if args[0] in ("apply", "am"):
                out += [f for a in args[1:] for f in patch_files(a, cwd)]
        elif verb == "patch":
            out += args + [f for a in args for f in patch_files(a, cwd)]
    return out


def check(call, profile_path, allowed_path, bet):
    profile = open(profile_path).read()  # an OSError here is a deny: main() catches everything
    if not safety_card.locked(profile):
        return None
    allowed = safety_card.allowed_areas(allowed_path, bet)  # an allow opens only the area it names
    tool, inp, cwd = call["tool_name"], call.get("tool_input") or {}, call.get("cwd") or os.getcwd()
    if tool in FILE_TOOLS:
        paths = [inp[FILE_TOOLS[tool]]]
    elif tool == "Bash":
        paths = bash_targets(inp.get("command", ""), cwd)
    else:
        return None
    hit = safety_card.touched(profile, [rel(p, cwd) for p in paths], allowed)
    if not hit:
        return None
    return (safety_card.stop_question(hit[0], bet or "this bet") +
            f" Edit nothing. Answer `BLOCKED: locked area {hit[0]}`.")


def main():
    profile_path = os.environ.get("DUALTRACK_LOCK_PROFILE")
    if not profile_path:
        return 0  # not a Dualtrack run
    try:
        reason = check(json.load(sys.stdin), profile_path, os.environ.get("DUALTRACK_LOCK_ALLOWED", ""), os.environ.get("DUALTRACK_LOCK_BET", ""))
    except Exception as e:  # fail closed: a guard that cannot read its rules does not wave an edit through
        reason = f"Stopped: the locked-area guard could not read its rules ({type(e).__name__}), so no edit was made."
    if reason:
        print(reason, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
