# Releasing Dualtrack

Each release will be signed twice: the git tag, and a manifest listing the SHA-256 of every file in it. Anyone can then check
a copy with `scripts/verify.py` and tell the real kit from a fork. No release is signed yet.

## One-time setup (the maker, once)

1. Make an SSH signing key. Keep the private half to yourself: `ssh-keygen -t ed25519 -f ~/.ssh/dualtrack-release -C dualtrack-release`.
2. Add one line to `release-signers` in this repo, by pull request: `dualtrack-release ` followed by the contents of `~/.ssh/dualtrack-release.pub` (the key type and the key, without the comment).
3. Publish the key's fingerprint (`ssh-keygen -lf ~/.ssh/dualtrack-release.pub`) where people can compare it, such as on the project's site. `verify.py` prints the fingerprint it checked; a fork can ship its own `release-signers`, so the fingerprint is what to compare.

## Each release

1. Merge to `main` with green checks. Start from a clean `main`.
2. Run `SIGNING_KEY=~/.ssh/dualtrack-release bash scripts/release.sh v1.2.0`. It writes the manifest, signs it, signs the tag, exports the tag and checks the export verifies. If the export does not verify, it removes the tag.
3. Push the tag and publish the release with the two files, using the two commands the script prints. The script itself pushes and publishes nothing.

## Checking a copy

Download `RELEASE-MANIFEST` and `RELEASE-MANIFEST.sig` from the release page, then in the copy:

    python3 scripts/verify.py . --manifest RELEASE-MANIFEST --sig RELEASE-MANIFEST.sig

It exits 0 and prints who signed it when every file matches. It exits 4 and names the files when anything differs, is missing or was added, or when the signature is not from the release key.
