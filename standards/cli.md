# Command line

For commands, scripts and their output. Numbered CLI-n. Based on the Command Line Interface
Guidelines at clig.dev, in our own words.

1. **Help**: `-h` and `--help` work on every command and subcommand, show usage first, then
   one example per common task.
2. **Exit codes**: 0 is success; non-zero codes are documented and stable; scripts can rely on them.
3. **Streams**: results to stdout, messages and errors to stderr; output stays usable in a pipe.
4. **Machine output**: where a script would parse it, offer `--json` or a stable plain format.
5. **No surprise prompts**: never block on input when stdin is not a terminal; every prompt
   has a flag that answers it.
6. **Dangerous actions**: confirm, or need `--force` / `--yes`; offer `--dry-run` where it fits.
7. **Errors**: one line saying what failed, then the exact command or step that fixes it.
   No stack trace unless asked for.
8. **Colour and symbols**: never the only carrier of meaning; honour `NO_COLOR` and non-TTY output.
9. **Progress**: anything over two seconds says it is working; long work says what step it is on.
10. **Names**: verbs for actions, consistent flags across commands, long flags readable,
    short flags only for common ones.
11. **Paths and setup**: say which files it reads and writes; never write outside the
    folders it names.
12. **Docs match**: the README's commands run as written, in the order written.
