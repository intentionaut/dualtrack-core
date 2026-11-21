#!/usr/bin/env python3
"""At Claude Code session start: say how to begin, only in a repo with no profile. Silent once set up (the plugin's SessionStart hook)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import decide

if not os.path.isfile(decide.find_profile()):
    print("Dualtrack is installed. Type /dualtrack:dualtrack to start.")
