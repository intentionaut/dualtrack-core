"""Temporary folders for tests, removed when the test process ends, so a run leaves nothing behind in $TMPDIR."""
import atexit
import shutil
import tempfile


def mkdtemp(**kw):
    d = tempfile.mkdtemp(**kw)
    atexit.register(shutil.rmtree, d, True)
    return d
