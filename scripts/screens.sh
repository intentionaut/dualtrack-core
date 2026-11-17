#!/bin/bash
# Render each page the change touched, headless, so UX review sees it. Run from the branch's checkout.
# Usage: bash scripts/screens.sh <run_dir>   (reads <run_dir>/diff.txt)
# Writes <run_dir>/screens.txt: first line `passed`, `none: <why>` or `failed: <why>`, then one screenshot path a line.
# Env: RENDER, the Playwright command (default npx -y playwright@1.64.1), installed on demand.
# shortcut: only static .html pages render, by file://; an app that needs a server has no page here, so it never auto-merges.
set -uo pipefail
RUN=${1:?usage: screens.sh <run_dir>}; OUT=$RUN/screens.txt
RENDER=${RENDER:-npx -y playwright@1.64.1}
pages=$(grep -Ev '^D' "$RUN/diff.txt" | cut -f2 | grep -Ei '\.html?$')
[ -n "$pages" ] || { echo "none: no changed page to render" > "$OUT"; exit 0; }
mkdir -p "$RUN/screens"
$RENDER install chromium > "$RUN/screens/install.log" 2>&1 || { echo "failed: could not install the browser (see screens/install.log)" > "$OUT"; exit 1; }
list=; n=0
while read -r page; do
  n=$((n + 1)); png="$RUN/screens/$n-$(basename "$page" | tr -c 'A-Za-z0-9.\n' -).png"
  $RENDER screenshot --full-page "file://$PWD/$page" "$png" > "$RUN/screens/$n.log" 2>&1 && [ -s "$png" ] \
    || { echo "failed: $page did not render (see screens/$n.log)" > "$OUT"; exit 1; }
  list="$list$png"$'\n'
done <<< "$pages"
printf 'passed\n%s' "$list" > "$OUT"
