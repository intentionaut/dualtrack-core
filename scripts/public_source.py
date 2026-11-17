#!/usr/bin/env python3
"""Public numbers for a product that has no analytics yet: GitHub stars, forks, views and clones, and package downloads.

  public_source.py <profile.md> <YYYY-MM-DD>     print sources/public.md, from the product repo's root

No model call and no key of its own: GitHub through the owner's `gh` sign-in, downloads from the registries' free,
public endpoints. Packages come from the profile's **Packages** line, such as `npm:kernic, pypi:dualtrack`.
Every number names where it came from and its window; a read that fails is listed under Could not be read.
"""
import json
import os
import re
import subprocess
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import profile_value

GH = os.environ.get("GH_BIN", "gh")
REGISTRIES = {  # name: (url for a package, how to read the count, window)
    "npm": ("https://api.npmjs.org/downloads/point/last-week/{}", lambda d: d["downloads"], "last 7 days"),
    "pypi": ("https://pypistats.org/api/packages/{}/recent", lambda d: d["data"]["last_week"], "last 7 days"),
}


def gh(path):
    r = subprocess.run([GH, "api", path], capture_output=True, text=True, timeout=30)
    if r.returncode:
        raise RuntimeError((r.stderr.strip().splitlines() or ["gh api failed"])[-1][:120])
    return json.loads(r.stdout)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "dualtrack-public-source"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def packages(profile_text):
    value = profile_value.field(profile_text, "Packages")
    out = []
    for p in (x.strip() for x in value.split(",") if x.strip()):
        kind, _, name = p.partition(":")
        if kind.lower() in REGISTRIES and re.fullmatch(r"[@A-Za-z0-9._/-]{1,214}", name.strip()):
            out.append((kind.lower(), name.strip()))
    return out


def read(profile_text, today, gh=gh, fetch=fetch):
    lines, unread = [], []
    try:
        repo = gh("repos/{owner}/{repo}")
        lines += [f"- GitHub stars: {repo['stargazers_count']} (gh api repos/{{owner}}/{{repo}}, stargazers_count, as of {today})",
                  f"- GitHub forks: {repo['forks_count']} (gh api repos/{{owner}}/{{repo}}, forks_count, as of {today})"]
    except Exception as e:
        unread.append(f"- GitHub repo, {e}")
    for kind in ("views", "clones"):
        try:  # needs push access; GitHub keeps 14 days
            d = gh(f"repos/{{owner}}/{{repo}}/traffic/{kind}")
            lines.append(f"- GitHub {kind}: {d['count']}, {d['uniques']} unique "
                         f"(gh api repos/{{owner}}/{{repo}}/traffic/{kind}, count and uniques, last 14 days)")
        except Exception as e:
            unread.append(f"- GitHub {kind}, {e}")
    for kind, name in packages(profile_text):
        url, count, window = REGISTRIES[kind]
        try:
            lines.append(f"- {kind} downloads of {name}: {int(count(fetch(url.format(name))))} ({url.format(name)}, {window})")
        except Exception as e:
            unread.append(f"- {kind} downloads of {name}, {str(e)[:120] or 'could not be read'}")
    return (f"# Source: public, {today}\n\n" + ("\n".join(lines) or "- none found") +
            "\n\nCould not be read:\n" + ("\n".join(unread) or "- none") + "\n")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__.strip())
        sys.exit(2)
    sys.stdout.write(read(open(sys.argv[1]).read(), sys.argv[2]))
