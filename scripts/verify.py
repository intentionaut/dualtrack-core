#!/usr/bin/env python3
"""Check a copy of Dualtrack against the maker's signature, so anyone can tell the real kit from a fork.

  verify.py [kit] --manifest RELEASE-MANIFEST --sig RELEASE-MANIFEST.sig [--signers FILE]
                  exit 0 when the manifest is signed by a key in the signers file and every file in the copy
                  matches it; exit 4 and name what failed otherwise
  verify.py manifest [kit]
                  print the manifest for a release: the SHA-256 of every file git tracks in the kit

The manifest and signature come from the release's page; scripts/release.sh makes them. The signers file defaults to
`release-signers` in the kit: one line, `dualtrack-release <key type> <public key>`. Check the key's fingerprint, which this
prints, against the one the maker publishes with each release: a fork can ship its own signers file.
"""
import hashlib
import os
import subprocess
import sys

NAMESPACE = "dualtrack-release"
SKIP = {".git"}  # __pycache__ is not skipped: an unchecked-hash .pyc runs in place of its source


def digest(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def manifest(kit):
    out = subprocess.run(["git", "-C", kit, "ls-files", "-z"], capture_output=True, text=True, check=True).stdout
    return "".join(f"{digest(os.path.join(kit, p))}  {p}\n" for p in sorted(x for x in out.split("\0") if x))


def parse(text):
    return dict((line[66:], line[:64]) for line in text.splitlines() if len(line) > 66)


def on_disk(kit):
    for d, dirs, files in os.walk(kit):
        dirs[:] = [x for x in dirs if x not in SKIP]
        for f in files:
            yield os.path.relpath(os.path.join(d, f), kit)


def verify(kit, manifest_path, sig_path, signers=None):
    """(True, a line saying who signed it) or (False, what failed)."""
    signers = signers or os.path.join(kit, "release-signers")
    try:
        text = open(manifest_path).read()
    except OSError:
        return False, f"the manifest {manifest_path} is missing, so this copy cannot be checked"
    if not os.path.isfile(signers):
        return False, "no release key is listed for this copy, so its signature cannot be checked"
    r = subprocess.run(["ssh-keygen", "-Y", "verify", "-f", signers, "-I", NAMESPACE, "-n", NAMESPACE, "-s", sig_path],
                       input=text, capture_output=True, text=True)
    if r.returncode:
        return False, "the manifest is not signed by the Dualtrack release key"
    pinned = parse(text)
    bad = sorted(p for p, h in pinned.items() if not os.path.isfile(os.path.join(kit, p)) or digest(os.path.join(kit, p)) != h)
    bad += sorted(p for p in on_disk(kit) if p not in pinned)
    if bad:
        return False, "this copy is not the signed release: " + ", ".join(bad[:5]) + (f" and {len(bad) - 5} more" if len(bad) > 5 else "") + " differ"
    return True, f"this is the signed Dualtrack release ({len(pinned)} files). " + r.stdout.strip()


def main(argv):
    if argv[:1] == ["manifest"]:
        print(manifest(argv[1] if len(argv) > 1 else "."), end="")
        return 0
    opts = {k: argv[i + 1] for i, k in enumerate(argv[:-1]) if k in ("--manifest", "--sig", "--signers")}
    rest = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or argv[i - 1] not in opts)]
    if "--manifest" not in opts or "--sig" not in opts:
        print(__doc__.strip())
        return 2
    ok, said = verify(rest[0] if rest else ".", opts["--manifest"], opts["--sig"], opts.get("--signers"))
    print(said)
    return 0 if ok else 4


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
