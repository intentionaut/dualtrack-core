#!/usr/bin/env python3
"""A one-hour GitHub App installation token for one repo, for company mode.

Usage: app_token.py <owner/repo>
Env:   DUALTRACK_APP_ID, and one of:
         DUALTRACK_APP_SIGNER  a command that reads the bytes to sign on stdin and writes the raw RSA SHA-256
                               signature to stdout, so the key stays in a key vault (Cloud KMS, AWS KMS, Key Vault)
                               and is never read here. Preferred, as GitHub recommends.
         DUALTRACK_APP_KEY     path to the App's private key, PEM, readable only by you. The weaker fallback.
       GITHUB_API (default https://api.github.com)

Prints the token. It is scoped to that repo and to what the loop needs: contents and pull requests to
write, issues to label, checks to post Dualtrack's review, statuses and the repo's rules to read. The App's own installation can grant no more than
the company allowed it. The JWT is signed with openssl, so no package is needed.
"""
import base64
import json
import os
import subprocess
import sys
import time
import urllib.request

# Checks to post Dualtrack's review beside CI; administration, read-only, to read the repo's rulesets and required checks.
PERMISSIONS = {"contents": "write", "pull_requests": "write", "issues": "write", "checks": "write", "statuses": "read",
               "administration": "read", "metadata": "read"}


def b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def jwt(app_id, key_path, now=None, signer=None):
    now = int(now or time.time())
    head = b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    # Backdated a minute for clock drift; GitHub allows ten minutes at most.
    body = b64(json.dumps({"iat": now - 60, "exp": now + 540, "iss": str(app_id)}).encode())
    cmd = signer if signer else ["openssl", "dgst", "-sha256", "-sign", key_path]
    sig = subprocess.run(cmd, input=f"{head}.{body}".encode(), capture_output=True, check=True, shell=isinstance(cmd, str)).stdout
    return f"{head}.{body}.{b64(sig)}"


def call(url, token, data=None):
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None,
                                 method="POST" if data is not None else "GET",
                                 headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                          "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def wanted(granted, warn=lambda m: sys.stderr.write(m + "\n")):
    """What the loop needs, cut to what the installation granted. Asking for more fails the whole token, so a
    missing grant costs only the feature that needs it, and says so."""
    out = {}
    for name, level in PERMISSIONS.items():
        have = granted.get(name)
        if have == level or (have == "write" and level == "read"):
            out[name] = level
        elif have == "read":
            out[name] = "read"; warn(f"the App can only read {name}; give it write for every feature")
        else:
            warn(f"the App has no {name} access; give it {level} for every feature")
    return out


def token(repo, env=os.environ):
    api = env.get("GITHUB_API", "https://api.github.com")
    signed = jwt(env["DUALTRACK_APP_ID"], env.get("DUALTRACK_APP_KEY"), signer=env.get("DUALTRACK_APP_SIGNER"))
    install = call(f"{api}/repos/{repo}/installation", signed)
    name = repo.split("/", 1)[1]
    return call(f"{api}/app/installations/{install['id']}/access_tokens", signed,
                {"repositories": [name], "permissions": wanted(install.get("permissions", {}))})["token"]


if __name__ == "__main__":
    if len(sys.argv) != 2 or "/" not in sys.argv[1]:
        sys.exit(__doc__.strip())
    if not os.environ.get("DUALTRACK_APP_ID") or not (os.environ.get("DUALTRACK_APP_SIGNER") or os.environ.get("DUALTRACK_APP_KEY")):
        sys.exit("company mode needs a GitHub App: set DUALTRACK_APP_ID, and DUALTRACK_APP_SIGNER or DUALTRACK_APP_KEY")
    try:
        print(token(sys.argv[1]))
    except Exception as e:  # any failure leaves the loop without GitHub access, which stops it
        sys.exit(f"could not get a GitHub App token for {sys.argv[1]}: {e}")
