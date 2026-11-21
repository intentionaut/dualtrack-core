#!/usr/bin/env python3
"""Write tests/affected.json, the map from changed files to the tests that cover them (INT-248).

  build_affected_map.py          rewrite tests/affected.json
  build_affected_map.py --check  exit 1 if the committed file differs from what this would write

How it seeds the map, from the repo's own text (no test is run):
  1. A file is "referenced" by a source file (a test, a script, a test helper) when the source text names its path or
     its basename, or imports it (`import X`, `from X`, `X.py`, a quoted "X") for a Python module. Directories in DIRS
     count when the source names `dir/` or quotes "dir".
  2. References are followed through scripts and helpers: a test that runs daily_loop.sh covers what daily_loop.sh runs.
  3. Each tracked file maps to every test module that reaches it. A file nothing reaches maps to [], safety set only.
Then the hand rules below. Over-matching is safe (it runs more tests); under-matching is the risk, so the match is loose.
Files not tracked or not listed stay out of the map on purpose: the selector runs everything for them.
"""
import ast
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "tests" / "affected.json"

# Hand rule: the tests that must run on every PR, found by name under tests/: sandbox, tamper / safety files, merge
# gate, injection / canary / exfil, egress, and the selector's own tests (a PR that edits a test's imports must see the
# map go stale). test_kit and test_secrets are cheap repo-wide checks. SAFETY_CLASSES add the sandbox classes in test_setup.
# SAFETY_SCAN modules are too big to run whole (test_loop is most of the suite), so only their tests whose name has one
# of SAFETY_WORDS as a word join the safety set, one id each. test_lock_hook is the locked-area block, so it always runs.
SAFETY = ["test_affected", "test_delayed_exfil", "test_egress", "test_encoded_exfil", "test_gates", "test_kit",
          "test_lock_hook", "test_merge_gate", "test_quarantine", "test_sandbox_escape", "test_secrets", "test_tamper", "test_verifier_sabotage"]
SAFETY_CLASSES = ["test_setup.NestedSandbox", "test_setup.OfflineBox"]
SAFETY_SCAN = ["test_loop", "test_setup", "test_handoff", "test_mcp_server"]
SAFETY_WORDS = {"sandbox", "seatbelt", "bubblewrap", "canary", "inject", "exfil", "egress", "tamper", "secret", "offline",
                "escape", "lock"}
# Hand rule (docs/test-value.md): slow tests on the five journeys that must never break, added to the always-run set.
# Others over 5s are NIGHTLY: skipped in pull request runs, run in every other run. The safety set above is critical too.
CRITICAL = [
    "test_loop.Loop.test_a_source_gets_back_its_own_server_and_nothing_else",
    "test_loop.Loop.test_a_star_alone_leaves_the_test_network_with_no_domains_and_stops",
    "test_loop.Loop.test_a_star_in_allowed_domains_is_dropped_for_the_agents_and_named_in_the_brief",
    "test_loop.Loop.test_branch_code_can_fstat_its_stdout_which_is_a_file_in_the_run_folder",
    "test_loop.Loop.test_branch_code_cannot_connect_to_a_unix_socket",
    "test_loop.Loop.test_branch_code_cannot_look_names_up",
    "test_loop.Loop.test_branch_code_cannot_look_names_up_with_test_network_on",
    "test_loop.Loop.test_branch_code_cannot_read_the_dashboard_launch_file",
    "test_loop.Loop.test_branch_code_cannot_write_outside_its_checkout",
    "test_loop.Loop.test_branch_code_still_writes_its_checkout_tmp_and_git",
    "test_loop.Loop.test_dashboard_folder_rule_leaves_the_rest_of_dualtrack_home_readable",
    "test_loop.Loop.test_setup_commands_can_look_names_up",
    "test_loop.Loop.test_setup_commands_do_not_get_a_link_to_the_owners_node_modules",
    "test_loop.Loop.test_setup_commands_still_cannot_connect_to_a_unix_socket",
    "test_loop.Loop.test_setup_token_reaches_the_setup_commands_only",
    "test_loop.Loop.test_setup_token_with_an_invalid_name_or_no_value_is_ignored",
    "test_loop.Loop.test_sources_run_with_only_their_read_only_tools",
    "test_loop.Loop.test_test_network_blocks_a_domain_not_allowed_and_names_it",
    "test_loop.Loop.test_test_network_on_closes_the_home_folder",
    "test_loop.Loop.test_test_network_on_closes_toolchain_logins",
    "test_loop.Loop.test_test_network_on_lets_tests_reach_the_internet",
    "test_loop.Loop.test_test_network_on_reads_toolchains",
    "test_loop.Loop.test_test_network_stops_code_that_skips_the_proxy",
    "test_loop.Loop.test_test_network_without_domains_stops",
    "test_loop.Loop.test_blocked_after_a_heading_and_blank_line_is_still_blocked",
    "test_loop.Loop.test_no_build_starts_without_budget_to_review_it",
    "test_loop.Loop.test_outside_comments_wait_when_the_reader_fails_or_the_run_is_a_preflight",
    "test_loop.Loop.test_a_run_going_on_another_machine_stops_this_one",
    "test_loop.Loop.test_a_home_path_in_a_finding_is_masked_not_dropped",
    "test_run.Run.test_two_takeovers_of_a_dead_lock_end_with_one_owner",
    "test_loop.Loop.test_setup_token_printed_by_a_failing_setup_is_blanked",
    "test_loop.Loop.test_render_failure_is_changes_never_a_pass",
    "test_loop.Loop.test_a_file_name_with_an_accent_is_still_checked",
    "test_loop.Loop.test_company_mode_sandboxes_every_agent_and_fails_closed",
    "test_loop.Loop.test_a_stranger_or_a_past_contributor_cannot_ask_for_changes",
    "test_loop.Loop.test_outside_comments_reach_the_team_only_as_checked_fields",
    "test_loop.Loop.test_branch_code_cannot_touch_the_files_the_checks_read",
    "test_loop.Loop.test_a_waiting_change_the_gate_still_holds_says_why",
    "test_loop.Loop.test_a_change_that_was_only_waiting_is_put_through_the_gate_again",
    "test_loop.DefaultRun",
    "test_loop.RejectRun",
    "test_loop.Loop.test_a_change_to_the_profile_is_held",
    "test_loop.Loop.test_a_deleting_line_holds_the_change",
    "test_loop.Loop.test_a_failed_install_in_the_fail_first_check_holds_the_merge",
    "test_loop.Loop.test_a_finding_with_personal_data_is_dropped_and_the_rest_kept",
    "test_loop.Loop.test_a_held_branch_that_changes_workflows_is_never_pushed",
    "test_loop.Loop.test_a_line_not_met_stops_before_the_pull_request_and_names_the_line",
    "test_loop.Loop.test_a_planted_order_never_reaches_the_team",
    "test_loop.Loop.test_a_public_repos_pull_request_never_shows_the_owners_numbers_emails_or_paths",
    "test_loop.Loop.test_a_red_branch_goes_back_to_the_engineer_before_any_review",
    "test_loop.Loop.test_a_setting_beside_tracking_lines_is_still_a_stop",
    "test_loop.Loop.test_a_setting_dressed_as_a_tracking_line_is_still_a_stop",
    "test_loop.Loop.test_a_signed_bet_is_built_and_checked_against_the_owners_lines_not_the_pms",
    "test_loop.Loop.test_a_tracked_record_inside_the_repo_stops_before_any_agent",
    "test_loop.Loop.test_an_agent_adding_claude_settings_or_instructions_is_held_and_undone",
    "test_loop.Loop.test_an_agent_planting_a_command_in_git_config_is_caught_and_undone",
    "test_loop.Loop.test_an_engineer_edit_to_the_profile_cannot_turn_on_auto_merge",
    "test_loop.Loop.test_an_unreadable_visibility_counts_as_public",
    "test_loop.Loop.test_auto_merge_with_every_check_merges_and_logs_how_to_undo",
    "test_loop.Loop.test_auto_merge_without_code_review_never_merges",
    "test_loop.Loop.test_baseline_a_new_failure_is_not_no_new_failures",
    "test_loop.Loop.test_baseline_with_the_same_failures_after_the_change_is_no_new_failures_and_never_auto_merges",
    "test_loop.Loop.test_branch_code_cannot_write_git_hooks_info_or_config_but_can_write_the_rest",
    "test_loop.Loop.test_branch_code_runs_without_keys_tokens_or_a_real_home",
    "test_loop.Loop.test_branch_tests_cannot_get_the_loops_own_git_to_run_a_command",
    "test_loop.Loop.test_changed_criteria_stop_before_the_pull_request",
    "test_loop.Loop.test_code_review_all_clear_counts_only_as_the_whole_answer",
    "test_loop.Loop.test_code_review_findings_leave_it_for_the_owner",
    "test_loop.Loop.test_company_mode_keeps_its_token_from_the_source_reader",
    "test_loop.Loop.test_company_mode_needs_the_app_and_no_agent_sees_its_token",
    "test_loop.Loop.test_company_mode_never_merges_even_with_every_check",
    "test_loop.Loop.test_confirmed_bet_is_built_and_closed",
    "test_loop.Loop.test_criteria_locked_when_the_item_is_parsed_and_unchanged_passes",
    "test_loop.Loop.test_fail_first_puts_back_code_whose_name_contains_test",
    "test_loop.Loop.test_git_settings_are_guarded_in_a_worktree_too",
    "test_loop.Loop.test_obedient_agent_stops_the_line_and_the_token_stays_out_of_the_brief",
    "test_loop.Loop.test_one_fix_round_then_opens",
    "test_loop.Loop.test_setup_commands_cannot_read_the_home_folder_but_can_write_the_checkout",
    "test_loop.Loop.test_setup_token_is_withheld_from_the_install_on_the_branchs_code",
    "test_loop.Loop.test_stop_list_on_the_diff",
    "test_loop.Loop.test_stop_list_on_the_item",
    "test_loop.Loop.test_tests_failing_on_the_base_stop_before_any_agent",
    "test_loop.Loop.test_the_planted_token_is_random_per_run",
]

NIGHTLY = [
    "test_loop.Loop.test_unknown_is_not_quiet",
    "test_decide.Decide.test_a_call_is_pushed_after_another_machine_pushed_first_and_sweeps_nothing_else",
    "test_dashboard_server.Server.test_a_silent_connection_does_not_hold_the_server",
    "test_loop.Areas.test_a_run_offers_the_fix_in_the_brief",
    "test_loop.KitSelfUpdate.test_a_kit_on_main_behind_its_remote_updates_itself_before_running",
    "test_loop.Loop.test_a_backlog_names_its_project_in_the_sources_ask",
    "test_loop.Loop.test_a_blocked_engineer_asks_and_the_answer_reaches_the_next_build",
    "test_loop.Loop.test_a_blocked_engineer_leaves_a_clean_tree_and_the_refusals_on_record",
    "test_loop.Loop.test_a_blocked_line_quoted_under_design_is_not_a_blocked_design",
    "test_loop.Loop.test_a_blocked_line_quoted_under_done_is_not_a_blocked_report",
    "test_loop.Loop.test_a_brief_pick_still_builds_the_runner_up",
    "test_loop.Loop.test_a_chained_test_command_gets_one_rule_per_part",
    "test_loop.Loop.test_a_confirmed_goal_is_not_asked_again_but_other_questions_stay",
    "test_loop.Loop.test_a_contact_email_in_code_still_pushes_on_a_public_repo",
    "test_loop.Loop.test_a_fetch_that_never_answers_stops_the_run_with_a_line_instead_of_hanging",
    "test_loop.Loop.test_a_held_clean_branch_is_pushed_for_the_next_run",
    "test_loop.Loop.test_a_killed_run_leaves_a_team_log_line_with_its_spend_and_a_fresh_brief",
    "test_loop.Loop.test_a_label_the_reader_never_called_is_flagged",
    "test_loop.Loop.test_a_master_default_branch_is_found",
    "test_loop.Loop.test_a_medium_or_long_item_no_one_sees_is_built_on_the_automatic_track",
    "test_loop.Loop.test_a_missing_or_empty_run_cap_becomes_10_and_the_run_goes_on",
    "test_loop.Loop.test_a_named_outside_reviewer_reaches_the_brief_and_the_quarantine_only",
    "test_loop.Loop.test_a_pick_already_built_is_closed_and_the_next_one_runs",
    "test_loop.Loop.test_a_pm_item_with_unprovable_lines_is_sent_back_once_then_builds",
    "test_loop.Loop.test_a_pull_request_that_cannot_be_opened_names_the_pushed_branch",
    "test_loop.Loop.test_a_real_image_still_pushes",
    "test_loop.Loop.test_a_refused_backlog_name_falls_back_to_the_normal_ask_and_says_why",
    "test_loop.Loop.test_a_reviewer_quoting_the_branch_does_not_stop_the_pull_request",
    "test_loop.Loop.test_a_reviewer_routed_to_the_engineers_model_runs_on_another",
    "test_loop.Loop.test_a_run_cut_short_after_the_build_resumes_at_review",
    "test_loop.Loop.test_a_runner_killed_at_start_is_not_called_a_failing_test",
    "test_loop.Loop.test_a_second_run_in_the_same_checkout_stops",
    "test_loop.Loop.test_a_source_health_problem_from_session_start_shows_in_the_brief",
    "test_loop.Loop.test_a_source_that_fails_is_named_and_the_run_goes_on",
    "test_loop.Loop.test_a_source_that_returns_no_numbers_says_so",
    "test_loop.Loop.test_a_source_with_no_numbers_does_not_count_toward_seams",
    "test_loop.Loop.test_a_state_checkout_with_an_edit_over_a_remote_change_stops_before_the_run",
    "test_loop.Loop.test_a_stopped_run_leaves_a_lesson_from_the_gate_table_not_the_outcome_text",
    "test_loop.Loop.test_a_test_command_that_never_returns_is_cut_off_and_the_run_says_so",
    "test_loop.Loop.test_a_visible_item_of_any_size_still_goes_to_the_owner",
    "test_loop.Loop.test_an_agent_call_that_never_returns_is_cut_off",
    "test_loop.Loop.test_an_engineer_that_needs_a_command_asks_and_the_branch_waits",
    "test_loop.Loop.test_an_explicit_run_cap_or_none_is_not_stopped",
    "test_loop.Loop.test_an_unknown_source_stops_before_any_agent",
    "test_loop.Loop.test_an_unreadable_intent_answer_stops_too",
    "test_loop.Loop.test_asks_already_answered_by_a_later_commit_wait",
    "test_loop.Loop.test_baseline_a_different_failure_is_a_different_issue",
    "test_loop.Loop.test_baseline_a_repeat_comments_on_the_open_issue_instead_of_a_new_one",
    "test_loop.Loop.test_baseline_red_here_and_in_ci_makes_getting_main_green_the_item",
    "test_loop.Loop.test_baseline_red_only_here_builds_the_planned_item_and_the_trail_says_ci_is_the_baseline",
    "test_loop.Loop.test_baseline_stop_names_the_failing_tests_and_files_one_labelled_issue",
    "test_loop.Loop.test_baseline_unreadable_names_fall_back_to_the_last_twenty_lines",
    "test_loop.Loop.test_blocked_bet_is_closed_so_it_does_not_repeat",
    "test_loop.Loop.test_blocked_design_builds_nothing",
    "test_loop.Loop.test_brief_is_never_built",
    "test_loop.Loop.test_claude_code_below_the_floor_stops_before_any_agent",
    "test_loop.Loop.test_company_mode_refuses_a_personal_plan_before_any_agent",
    "test_loop.Loop.test_confirmed_bet_skips_research",
    "test_loop.Loop.test_cost_cap_in_the_environment_overrides_a_missing_run_cap",
    "test_loop.Loop.test_decide_holds_after_a_second_bad_line_and_keeps_the_answer",
    "test_loop.Loop.test_decide_retries_once_on_a_bad_status_line",
    "test_loop.Loop.test_decide_retries_once_with_the_filers_reason",
    "test_loop.Loop.test_design_checks_reach_ux_review",
    "test_loop.Loop.test_design_rules_never_reach_a_cli_item",
    "test_loop.Loop.test_design_rules_not_installed_stops",
    "test_loop.Loop.test_design_rules_reach_a_web_item_behind_the_product",
    "test_loop.Loop.test_docs_only_change_opens",
    "test_loop.Loop.test_engineer_leaving_the_branch_stops",
    "test_loop.Loop.test_engineer_rules_follow_the_engineer_prompt_when_chosen",
    "test_loop.Loop.test_every_run_leaves_an_event_and_posts_it_to_the_webhook",
    "test_loop.Loop.test_first_run_skips_watch",
    "test_loop.Loop.test_ignoring_a_confirmed_bet_is_held",
    "test_loop.Loop.test_inline_comments_count_as_asks_too",
    "test_loop.Loop.test_item_must_match_the_memo_move",
    "test_loop.Loop.test_item_without_a_decision_opens_nothing",
    "test_loop.Loop.test_lines_still_unprovable_after_the_rewrite_stop_with_a_plain_reason",
    "test_loop.Loop.test_linked_dependencies_ignored_with_a_slash_do_not_dirty_the_teams_tree",
    "test_loop.Loop.test_low_level_change_a_visitor_would_see_opens_with_a_note",
    "test_loop.Loop.test_no_commit_without_done_still_closes_the_pick_and_keeps_the_answer",
    "test_loop.Loop.test_no_engineer_rules_means_the_kit_prompt_and_reading_rules_alone",
    "test_loop.Loop.test_no_item_opens_nothing",
    "test_loop.Loop.test_null_on_a_confirmed_bet_is_not_quiet",
    "test_loop.Loop.test_one_open_change_at_a_time",
    "test_loop.Loop.test_owner_asks_on_the_open_change_are_built_on_its_branch",
    "test_loop.Loop.test_pauses_after_two_rejections",
    "test_loop.Loop.test_ponytail_not_installed_says_how_to_install_it",
    "test_loop.Loop.test_ponytail_runs_only_at_the_pinned_version",
    "test_loop.Loop.test_ponytail_with_no_version_is_pinned_to_the_installed_one",
    "test_loop.Loop.test_preflight_checks_for_free",
    "test_loop.Loop.test_preflight_files_no_issue",
    "test_loop.Loop.test_profile_routing_picks_the_model",
    "test_loop.Loop.test_quiet_day_opens_nothing",
    "test_loop.Loop.test_rejected_pick_opens_nothing",
    "test_loop.Loop.test_release_notes_that_break_the_guideline_are_held",
    "test_loop.Loop.test_run_cap_none_means_no_cap",
    "test_loop.Loop.test_seams_across_two_sources_lead_the_brief_and_one_source_lines_do_not",
    "test_loop.Loop.test_setup_commands_run_first_and_a_failure_stops_for_free",
    "test_loop.Loop.test_setup_none_with_a_note_runs_nothing_in_any_case",
    "test_loop.Loop.test_setup_questions_stay_in_the_brief",
    "test_loop.Loop.test_small_docs_change_gets_one_reviewer_not_on_the_engineers_model",
    "test_loop.Loop.test_state_repo_gets_the_record_and_the_product_repo_does_not",
    "test_loop.Loop.test_tests_and_docs_change_opens_and_says_so",
    "test_loop.Loop.test_tests_that_finish_inside_the_timeout_are_left_alone",
    "test_loop.Loop.test_tests_that_pass_without_the_change_open_with_a_note",
    "test_loop.Loop.test_the_audit_runs_once_a_week",
    "test_loop.Loop.test_the_floor_version_and_newer_pass",
    "test_loop.Loop.test_the_owners_open_work_never_blocks_a_run_and_is_left_alone",
    "test_loop.Loop.test_the_same_text_on_a_private_repo_still_opens",
    "test_loop.Loop.test_the_word_ponytail_finds_the_installed_plugin",
    "test_loop.Loop.test_tracking_lines_another_session_writes_are_not_a_stop",
    "test_loop.Loop.test_two_sources_and_no_seam_is_said",
    "test_loop.Loop.test_ux_changes_twice_stops",
    "test_loop.Loop.test_visible_bet_gets_a_ux_review_in_the_trail",
    "test_loop.Loop.test_visible_bet_is_designed_first_by_its_surfaces",
    "test_loop.Loop.test_visible_change_is_built_before_the_pick",
    "test_loop.Loop.test_web_change_is_rendered_for_ux_review",
    "test_loop.Loop.test_whitespace_only_change_to_the_criteria_passes",
    "test_loop.Loop.test_with_a_remote_that_cannot_be_reached_the_run_still_stops",
    "test_loop.Loop.test_without_github_preflight_is_ready",
    "test_loop.Loop.test_without_github_the_run_brings_the_brief_and_stops_before_building",
    "test_run.Run.test_a_first_run_pushes_its_record_to_the_state_repo",
    "test_run.Run.test_a_killed_run_leaves_a_team_log_line",
    "test_run.Run.test_a_record_the_state_repo_refuses_fails_the_run",
    "test_run.Run.test_a_run_from_a_subfolder_saves_to_the_state_repo_not_the_product_repo",
    "test_run.Run.test_a_second_run_at_once_stops_instead_of_losing_its_record",
    "test_run.Run.test_a_state_push_that_never_answers_is_cut_off_and_names_the_next_step",
    "test_run.Run.test_a_state_repo_run_files_where_the_loop_reads",
    "test_setup.Setup.test_a_new_state_repo_is_named_in_plain_words_when_made",
    "test_setup.Setup.test_state_record_is_filed_beside_the_repo_and_pushed",
]
# Hand rule: docs are mapped only by name; any other docs file needs no test beyond the safety set.
DOC_GLOB = "docs/*"
# Directories whose files tests read by walking or globbing, not by naming each one.
DIRS = ["agents", "skills", "standards", "prompts", "hooks", "evals", "commands-adapted", "product-context", "example",
        "benchmarks", ".claude-plugin"]


def tracked():
    r = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT, capture_output=True,
                       text=True, check=True)
    return sorted({f for f in r.stdout.splitlines() if f and (ROOT / f).is_file()})


def sources(files):
    return [f for f in files if re.fullmatch(r"(scripts|tests)/[\w.-]+\.(py|sh)", f)]


def refs(text, files, src, loose=True):
    """The files `text` (of `src`) refers to. loose=False is the strict reading used between scripts."""
    if not loose:
        return strict_refs(text, files, src)
    out = set()
    for f in files:
        if f == src:
            continue
        p = Path(f)
        if p.suffix == ".py" and p.parts[0] in ("scripts", "tests"):
            s = re.escape(p.stem)
            if re.search(rf"(?:^|[^\w])(?:import|from)\s+(?:tests\.)?{s}\b|\b{s}\.py\b|[\"']{s}[\"']", text, re.M):
                out.add(f)
        elif f in text or re.search(r"(?<![\w/.-])" + re.escape(p.name) + r"\b", text):
            out.add(f)
    for d in DIRS:
        if re.search(rf"(?<![\w-]){re.escape(d)}/|[\"']{re.escape(d)}[\"']", text):
            out.update(f for f in files if f.startswith(d + "/"))
    return out


def strict_refs(text, files, src):
    """Between scripts only what runs counts, not what a comment or docstring names: a Python script's imports and its
    string literals that are a script path; a shell script's non-comment lines that name a script file."""
    scripts = [f for f in files if f != src and re.fullmatch(r"(scripts/[\w-]+\.\w+|tests/[\w-]+\.py)", f)]
    out = set()
    if src.endswith(".py"):
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return set(scripts)  # cannot read it: assume it reaches everything
        names, lits = set(), []
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                names.update(a.name.split(".")[-1] for a in n.names)
            elif isinstance(n, ast.ImportFrom):
                names.update([(n.module or "").split(".")[-1], *(a.name for a in n.names)])
            elif isinstance(n, ast.Constant) and isinstance(n.value, str) and len(n.value) < 200:
                lits.append(n.value)
        for f in scripts:
            stem = Path(f).stem
            if (f.endswith(".py") and stem in names) or any(re.fullmatch(rf"(?:.*[/\s])?{re.escape(Path(f).name)}", v) for v in lits):
                out.add(f)
    else:
        code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
        out.update(f for f in scripts if re.search(rf"(?<![\w.-]){re.escape(Path(f).name)}\b", code))
    return out


def safety_ids():
    """Ids of the safety tests inside the big modules: any test whose name has a SAFETY_WORDS word in it."""
    out = []
    for mod in SAFETY_SCAN:
        for cls in ast.parse((ROOT / "tests" / f"{mod}.py").read_text()).body:
            if isinstance(cls, ast.ClassDef):
                out += [f"{mod}.{cls.name}.{fn.name}" for fn in cls.body
                        if isinstance(fn, ast.FunctionDef) and fn.name.startswith("test")
                        and SAFETY_WORDS & set(fn.name.split("_"))]
    return out


def build():
    files = tracked()
    texts = {s: (ROOT / s).read_text(errors="replace") for s in sources(files)}
    # Tests name anything loosely. Between files, only imports and script names carry: a looser edge spreads every test to every file.
    graph = {s: refs(t, files, s, loose=s.startswith("tests/test_")) for s, t in texts.items()}
    tests = {f: Path(f).stem for f in files if re.fullmatch(r"tests/test_[\w]+\.py", f)}
    reach = {}  # file -> test modules that reach it
    for tf, mod in tests.items():
        seen, todo = {tf}, [tf]
        while todo:
            for nxt in graph.get(todo.pop(), ()):
                if nxt not in seen:
                    seen.add(nxt)
                    todo.append(nxt)
        for f in seen:
            reach.setdefault(f, set()).add(mod)
    amap = {}
    for f in files:
        mods = set(reach.get(f, ()))
        if f.startswith("scripts/") and f.endswith(".py"):
            mods.add("test_py39_syntax")  # compiles every script on an older Python
        if f in tests:
            mods.add("test_scratch")  # scans every test module for unscrubbed temp folders
        amap[f] = sorted(mods)
    if "tests/durations.json" in amap:
        amap["tests/durations.json"] = ["test_parallel_queue"]  # timing data only: it changes order, never what runs
    amap[DOC_GLOB] = []
    safety = sorted(SAFETY + SAFETY_CLASSES + safety_ids())
    both = sorted(set(NIGHTLY) & set(CRITICAL + safety))
    if both:
        raise SystemExit(f"nightly and critical at once: {both[:3]}")
    return {"safety": safety, "critical": sorted(CRITICAL), "nightly": sorted(NIGHTLY), "map": dict(sorted(amap.items()))}


def render(data):
    lines = ['{', f'  "safety": {json.dumps(data["safety"])},', f'  "critical": {json.dumps(data["critical"])},',
             f'  "nightly": {json.dumps(data["nightly"])},', '  "map": {']
    items = [f"    {json.dumps(k)}: {json.dumps(v)}" for k, v in data["map"].items()]
    return "\n".join(lines + [",\n".join(items), "  }", "}"]) + "\n"


def main(argv):
    text = render(build())
    if argv[1:] == ["--check"]:
        if not OUT.exists() or OUT.read_text() != text:
            print("tests/affected.json is stale: run `python3 scripts/build_affected_map.py` and commit it")
            return 1
        return 0
    OUT.write_text(text)
    print(f"wrote {OUT.relative_to(ROOT)}: {len(json.loads(text)['map'])} entries")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
