#!/usr/bin/env python3
"""limit.py <seconds> <command...>: run a command in its own process group and kill the whole group on timeout, TERM
or INT. 0 means no limit. Exit: the command's own, 124 on timeout, 128+signal when told to stop. Portable: macOS has
no timeout(1), and killing only the first process leaves its children running."""
import os
import signal
import subprocess
import sys
import time

seconds = float(sys.argv[1])
child = subprocess.Popen(sys.argv[2:], start_new_session=True)
told = []
for sig in (signal.SIGTERM, signal.SIGINT):
    signal.signal(sig, lambda n, f: told.append(n))


def group(sig):
    try:
        os.killpg(child.pid, sig)
    except ProcessLookupError:
        pass


end = time.time() + seconds if seconds else None
code = None
kill_at = None
while child.poll() is None:
    now = time.time()
    if code is None and (told or (end and now > end)):
        code = 128 + told[0] if told else 124
        if not told:
            print(f"timed out after {sys.argv[1]}s", file=sys.stderr)
        group(signal.SIGTERM)
        kill_at = now + 30  # the command gets time to clean up, then the group goes
    elif kill_at and now > kill_at:
        group(signal.SIGKILL)
    time.sleep(0.1)
group(signal.SIGKILL)  # nothing the command started outlives it
sys.exit(code if code is not None else child.returncode)
