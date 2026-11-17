# Component checklists

The definition of done for common parts. A design names the checklists it touches; UX review
checks each line. Numbered by part, such as BTN-2.

**Button (BTN)**
1. The label says the action as a verb.
2. One primary action per view.
3. Disabled only with a visible reason; prefer explaining over disabling.
4. Shows progress while working, and cannot be triggered twice.

**Form (FRM)**
1. Labels above or beside fields, never inside only.
2. Required and optional marked once, consistently.
3. Validation on submit or leaving a field, never on every keystroke.
4. Errors say how to fix it, next to the field, and a summary at the top for long forms.
5. Nothing typed is lost on error or back.

**Navigation (NAV)**
1. The current place is shown.
2. The same items in the same order everywhere.
3. Every page reachable within three steps from the start.

**Loading (LOAD)**
1. Over one second: show something is happening. Over ten: show progress and a way out.
2. Layout does not jump when content arrives.

**Empty state (EMPTY)**
1. Says why it is empty and the one next step.

**Error state (ERR)**
1. Says what happened, why if known, and the exact next step, in the person's words.
2. Never blames the person; never shows a raw code without a plain line.

**Table (TBL)**
1. Column headers name the unit.
2. Sorted by what people scan for; sort state shown.
3. Works narrow: scrolls inside itself or stacks.

**Command (CMD)**, for command-line tools, with `cli.md`
1. `--help` shows usage, then one example per common task.
2. A dangerous command confirms or needs `--yes`, and offers `--dry-run`.
3. Output works piped; errors go to stderr with a non-zero exit code.
