# Security policy

Dualtrack is a kit of scripts and agent prompts that runs a daily product loop on the owner's own machine. This page says how to report a security problem and what counts as one.

## Report a problem

Report privately. Do not open a public issue or pull request for a security problem.

1. Use GitHub private vulnerability reporting: open this repository's **Security** tab, then choose **Report a vulnerability**.
2. If that is unavailable, email `hello@intentionaut.com` with "Dualtrack security" in the subject.

Include the kit version (the `version` in `.claude-plugin/plugin.json`), the steps to reproduce, and what the problem lets someone do. Do not include real keys, tokens or customer data.

## In scope

- The loop scripts in `scripts/` (`daily_loop.sh`, `run.sh`, `loop_lib.py`, `guards.sh` and the others).
- The sandbox that runs code from a branch, and its checks.
- The egress proxy (`scripts/egress_proxy.py`) and the allowed-domains rule.
- The dashboard (`scripts/dashboard.py`, `scripts/dashboard_server.py`).
- The owner's decision step (`scripts/decide.py`) and the merge gate (`scripts/merge_gate.py`).
- Any path that leaks a secret, runs untrusted input as an instruction, writes outside the checkout, or merges without the owner's call.

## Out of scope

- Third-party models, Claude Code itself, GitHub, and other services the kit calls. Report those to their own maintainers.
- A product repo's own code. Dualtrack only reads and changes it as the owner directs.
- Problems that need an attacker who already has the owner's machine, shell or GitHub login.

## Reply time

First reply within 5 working days.

## Supported versions

Only the latest release is supported. Fixes go into the next release; older releases do not get patches.

## How each guard is tested

Each row says where the guard lives on `main`, the test that proves it, and the CI job that runs it. Line numbers drift as the files change, so search for the name if a line is off. The `test` job (`.github/workflows/test.yml`) runs the whole suite on Ubuntu with bubblewrap installed. The `seatbelt` job (`.github/workflows/macos.yml`) runs the Seatbelt tests on macOS, nightly and on pull requests that touch the sandbox; it is not a required check. Seatbelt tests skip on Ubuntu, and bubblewrap tests skip on macOS. Where a row says "no test", nothing checks that part.

| Guard | Where it lives | Test that proves it | CI job |
| --- | --- | --- | --- |
| Tamper pin: a changed safety file stops the run before anything is built | `scripts/tamper.py:33` and `:66`; called at `scripts/daily_loop.sh:16` | `tests/test_tamper.py::test_editing_any_listed_file_names_it_in_a_plain_message`, `::test_the_daily_loop_stops_before_any_work_when_a_safety_file_changed`, `::test_a_file_and_its_hash_changed_together_but_not_committed_stops_it` | `test` |
| Seatbelt sandbox for branch code (no network, no home secrets, writes only to the checkout) | `scripts/daily_loop.sh:303`, `:317`, `:368` | `tests/test_loop.py::test_branch_code_cannot_write_outside_its_checkout`, `::test_test_network_off_keeps_tests_offline`, `::test_branch_code_cannot_connect_to_a_unix_socket`, `::test_test_network_on_closes_the_home_folder` | `seatbelt` |
| bubblewrap sandbox, with `--unshare-net` and the proxy bridge | `scripts/daily_loop.sh:341`, `:329`, `:331`; `scripts/egress_bridge.py` | `tests/test_loop.py::test_on_linux_branch_code_is_offline_and_cannot_write_outside_its_checkout`, `::test_on_linux_test_network_on_enforces_the_proxy`; `tests/test_egress.py::test_the_bridge_carries_a_request_to_the_proxys_unix_socket_and_the_rules_still_hold` | `test` |
| No sandbox: the run stops unless the profile says `**Sandbox:** none, I accept the risk`; Company mode ignores that opt-in | `scripts/daily_loop.sh:404`, `:411`-`:413` | `tests/test_loop.py::test_no_sandbox_stops_before_any_agent_unless_the_profile_accepts_it`, `::test_company_mode_ignores_the_no_sandbox_opt_in` | `test` |
| Egress proxy: allowlist | `scripts/egress_proxy.py:27`, `:37` | `tests/test_egress.py::test_a_host_not_allowed_is_refused_and_logged`, `::test_subdomains_match_and_lookalikes_do_not`, `::test_only_ports_80_and_443_unless_the_entry_names_one` | `test` |
| Egress proxy: non-global addresses refused (loopback, private, link-local, metadata) | `scripts/egress_proxy.py:51` | `tests/test_egress.py::test_private_loopback_and_metadata_addresses_are_refused_unless_named_exactly` | `test` |
| Egress proxy: DNS rebinding (one lookup, then connect to that address) | `scripts/egress_proxy.py:51`, `:123` | `tests/test_egress.py::test_a_name_that_answers_differently_the_second_time_is_connected_once_to_the_first_answer` (a host an Allowed entry names exactly is the owner's own and connects by name) | `test` |
| Egress proxy: `*` in Allowed domains is refused for branch code and agents (only setup's learn mode, `--learn`, allows every host); the brief names it | `scripts/egress_proxy.py` (`parse_domains`), `scripts/daily_loop.sh` (`STAR`), `scripts/setup_check.py` | `tests/test_egress.py::test_a_star_entry_opens_the_proxy_only_in_learn_mode`, `::test_setup_starts_its_proxy_in_learn_mode_and_nothing_else_passes_the_flag`; `tests/test_loop.py::test_a_star_in_allowed_domains_is_dropped_for_the_agents_and_named_in_the_brief`, `::test_a_star_alone_leaves_the_test_network_with_no_domains_and_stops` | `test` |
| Canary token tripwire | `scripts/daily_loop.sh:27`, `:28`, `:675`, `:1007` | `tests/test_loop.py::test_a_leaked_canary_holds_the_change_and_tells_the_owner`, `::test_a_canary_in_the_record_is_reported_and_blanked_on_any_stop` | `test` |
| Git `config`, `hooks` and `info` cannot be written by branch code | `scripts/daily_loop.sh:358` (bubblewrap), `:374`-`:375` (Seatbelt) | `tests/test_loop.py::test_branch_code_cannot_write_git_hooks_info_or_config_but_can_write_the_rest` | `test` (bubblewrap), `seatbelt` |
| Git settings checked after every agent turn, and put back | `scripts/daily_loop.sh:236`-`:241` | `tests/test_loop.py::test_an_agent_planting_a_command_in_git_config_is_caught_and_undone`, `::test_git_settings_are_guarded_in_a_worktree_too` | `test` |
| gitguard uses SHA-256, not a 32-bit checksum | `scripts/daily_loop.sh:237` | `tests/test_loop.py::test_the_git_settings_check_is_not_fooled_by_a_forged_checksum` | `test` |
| Agent settings files (`CLAUDE.md`, `.claude/`, `.mcp.json`) put back if an agent changes them | `scripts/daily_loop.sh:248` | `tests/test_loop.py::test_an_agent_adding_claude_settings_or_instructions_is_held_and_undone` | `test` |
| Secret scanner (token shapes, connection strings, base64, hex and %-encoded text) | `scripts/loop_lib.py:941`, `:981`; run on the push at `scripts/daily_loop.sh:1013` | `tests/test_secrets.py::test_live_token_shapes_are_caught`, `::test_kept_cases_pass`; `tests/test_loop.py::test_a_wrapped_or_hidden_secret_is_still_a_secret`, `::test_a_secret_added_then_removed_is_never_pushed` | `test` |
| Merge gate: size (50 lines, 3 files, 20,000 bytes) | `scripts/merge_gate.py:22`, `:121` | `tests/test_merge_gate.py::test_3_size`, `::test_3_bytes_symlinks_and_modes` | `test` |
| Merge gate: risky paths | `scripts/merge_gate.py:24`, `:57` | `tests/test_merge_gate.py::test_2_risky_files_are_named`, `::test_2_tool_config_and_bare_github_are_risky` | `test` |
| Merge gate: prompts, hooks and safety files are never auto-merged (a person decides) | `scripts/merge_gate.py:24` (`an agent prompt`, `a hook`, `a safety file`) | `tests/test_merge_gate.py::test_2_agent_prompts_hooks_and_safety_files_are_never_auto_merged` | `test` |
| Dashboard: Host and Origin checked, launch secret on the page, token on every call | `scripts/dashboard_server.py:78`, `:92` | `tests/test_dashboard_server.py::test_a_refused_call_runs_nothing` (other origin, no origin, rebinding host), `::test_the_page_and_token_need_the_launch_secret`, `::test_a_post_still_needs_the_token_even_with_the_secret` | `test` |
| Setup token withheld from the install that runs branch code | `scripts/daily_loop.sh:48`, `:314`, `:501` | `tests/test_loop.py::test_setup_token_is_withheld_from_the_install_on_the_branchs_code`, `::test_setup_token_reaches_the_setup_commands_only` | `test` |

## Injection eval

The latest result is the row for 15 November 2026, kit `9c512e0`: 7 of 7 checks held. `evals/injection/results.jsonl` is appended in date order, so the last row is the latest; the file has 16 rows at this commit. Five rows from 14 November (kit `9c436e1`) show 6 of 7, with "the PR does not claim approval" failing; that check matched quoted planted text and was corrected before the 15 November run. Each row is one run on one model mix. It is not a rate.

## Known limits

- The tamper manifest (`safety-files.json`) can be re-pinned by anyone who can commit to the kit.
- The dashboard launch secret is visible in the address bar and in browser history.
- A GitHub App key file is a weaker fallback than KMS signing, and App keys do not expire.
- Read, Edit and WebFetch run outside the shell sandbox. Only deny lists limit them.
- There has been no outside penetration test and no certification.
- One maintainer.
