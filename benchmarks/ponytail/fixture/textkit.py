"""Small text helpers used by a command-line tool."""


def slugify(text):
    return "-".join(text.lower().split())


def truncate(text, limit):
    return text[:limit] + "..."


def wrap(text, width):
    lines, line = [], ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    return lines + [line] if line else lines
