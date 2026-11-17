"""One reader for profile values, so every script reads the same value from the same line. Stdlib only.

Setup writes a note beside a value it inferred or confirmed: `**Repo:** . (confirmed: run)`.
The note is for the owner; scripts read the value without it.
"""
import re

# A note is brackets that open with one of setup's words; it may hold one level of brackets of its own.
NOTE = re.compile(r"\s*\((?:inferred|confirmed|assumed|default|guessed)\b[^()]*(?:\([^()]*\)[^()]*)*\)", re.I)


def clean(value):
    return NOTE.sub("", value.replace("\r", "")).strip()


def field(text, name):
    m = re.search(rf"^\*\*{re.escape(name)}:\*\* *(.*)$", text, re.M)
    return clean(m[1]) if m else ""


if __name__ == "__main__":
    import sys
    try:
        text = open(sys.argv[1]).read()
    except OSError:
        text = ""
    print(field(text, sys.argv[2]))
