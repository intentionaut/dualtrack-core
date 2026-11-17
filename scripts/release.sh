#!/bin/bash
# Make a signed release: a signed tag, plus the signed manifest `verify.py` checks a copy against.
#
# Usage: SIGNING_KEY=<path to your private ssh signing key> bash scripts/release.sh <version, such as v1.2.0>
#
# It signs and tags on this machine only. It pushes nothing and publishes nothing: the last lines say the two commands that do.
set -euo pipefail
VERSION=${1:?usage: SIGNING_KEY=<key> release.sh <version>}
KEY=${SIGNING_KEY:?set SIGNING_KEY to the path of your private ssh signing key; this script never makes one}
KIT=$(cd "$(dirname "$0")/.." && pwd)
cd "$KIT"
[ -f "$KEY" ] || { echo "stopped: no key at $KEY"; exit 1; }
[ -z "$(git status --porcelain)" ] || { echo "stopped: the working tree has changes; a release is a clean commit"; exit 1; }
[ "$(git rev-parse --abbrev-ref HEAD)" = main ] || { echo "stopped: release from main"; exit 1; }
[ -f release-signers ] || { echo "stopped: release-signers is not in the repo yet; add your public key there first"; exit 1; }
OUT=$(mktemp -d)
python3 scripts/verify.py manifest . > "$OUT/RELEASE-MANIFEST"
ssh-keygen -Y sign -f "$KEY" -n dualtrack-release "$OUT/RELEASE-MANIFEST" > /dev/null
git -c gpg.format=ssh -c user.signingkey="$KEY" tag -s "$VERSION" -m "Dualtrack $VERSION"
# The release must verify from a clean export of the tag before anyone is told about it.
CHECK=$(mktemp -d); git archive "$VERSION" | tar -x -C "$CHECK"
python3 scripts/verify.py "$CHECK" --manifest "$OUT/RELEASE-MANIFEST" --sig "$OUT/RELEASE-MANIFEST.sig" --signers release-signers \
  || { git tag -d "$VERSION" > /dev/null; echo "stopped: the release did not verify, so the tag was removed"; exit 1; }
echo "signed $VERSION. Manifest and signature: $OUT"
echo "To publish: git push origin $VERSION && gh release create $VERSION $OUT/RELEASE-MANIFEST $OUT/RELEASE-MANIFEST.sig"
