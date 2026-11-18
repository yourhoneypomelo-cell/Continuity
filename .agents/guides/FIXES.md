# Fixes

Each fixed defect and the regression test that keeps it fixed. "fails" means the test fails on the previous
release, so it shows the defect; "guard" means it keeps a fix from being undone. The static tier checks that
every test named here exists.

Fixes through 3.6 are in [FIXES-3.6.md](FIXES-3.6.md).

| Version | Problem | Test | On the previous release |
| --- | --- | --- | --- |
| 3.7.0 | A change of the test-output parser would have made the sealed evidence of every project invalid | `test_regressions.Evidence.test_13_rules_1_evidence_stays_valid_after_a_parser_change` | fails |
| 3.7.0 | A summary edited by hand is still rejected under the rules the evidence recorded | `test_regressions.Evidence.test_13_forged_summary_is_still_rejected` | guard |
| 3.7.0 | Evidence read with newer rules than the tool knows was not told apart from a tampered file | `test_regressions.Evidence.test_13_newer_rules_are_refused_with_an_upgrade_hint` | fails |
| 3.7.0 | Rules 1 keep reading evidence exactly as 3.6.x did | `test_regressions.Evidence.test_13_frozen_rules_1_golden_outputs` | guard |
| 3.7.0 | Evidence that passed under older rules but fails under the current ones went unnoticed | `test_regressions.Evidence.test_13_older_rules_are_rechecked_with_a_note` | fails |
| 3.7.0 | An "OK" printed by the program under test made a passing unittest run unreadable | `test_regressions.Evidence.test_v3_program_printing_ok_keeps_the_unittest_summary` | fails |
| 3.7.0 | A log line starting with "FAILED" counted as a test failure | `test_regressions.Evidence.test_failed_log_line_is_not_a_test_failure` | fails |
| 3.7.0 | Enabling Gemini hooks on a released workspace left it NOT READY until a new session checkpointed | `test_upgrade.Rebaseline.test_hooks_enable_on_a_released_workspace_keeps_it_ready` | fails |
| 3.7.0 | A rebaseline takes in template files only, so other drift is still reported | `test_upgrade.Rebaseline.test_rebaseline_keeps_other_drift` | guard |
| 3.7.0 | A rebaseline refuses project files | `test_upgrade.Rebaseline.test_rebaseline_takes_only_template_files` | guard |
| 3.7.0 | A rebaseline waits until the workspace is released | `test_upgrade.Rebaseline.test_rebaseline_needs_a_released_workspace` | guard |
| 3.7.0 | There was no way to take the tool's hooks out of a host settings file | `test_regressions.Install.test_x3_hooks_disable_restores_the_settings_file` | fails |
| 3.7.0 | `install --merge` showed no preview of a merge and kept no copy of the merged files | `test_regressions.Install.test_x3_merge_dry_run_prints_a_diff` | fails |
| 3.7.0 | An install with --allow-modified recorded the template's hashes, not those of the files it copied | `test_regressions.Install.test_manifest_matches_written_files` | fails |
| 3.7.0 | Migrated v2 tasks lost their requirement IDs in CLOSED_ITEMS, so coverage dropped after a migration | `test_distribution.Migration.test_14_migrated_closed_tasks_keep_requirement_ids` | fails |
| 3.7.0 | Coverage counted every requirement ID anywhere in a closed task's text, so "leave R2 for later" verified R2 | `test_distribution.Migration.test_s4_coverage_reads_only_the_requirement_prefix` | fails |
| 3.7.0 | Tasks verified under continuity.v2 counted as verified in v3 without a run | `test_distribution.Migration.test_v2_closed_rows_are_counted_apart` | fails |
| 3.7.0 | Projects had no upgrade command: files were copied by hand, and guides the project had edited were overwritten | `test_upgrade.Upgrade.test_replaces_unmodified_and_keeps_modified_guides` | fails |
| 3.7.0 | Hook commands written by an older release were never updated in a project; an upgrade rewrites only the tool's entries | `test_upgrade.Upgrade.test_regenerates_only_our_hook_entries` | fails |
| 3.7.0 | An upgrade dry run writes nothing, not even the cache | `test_upgrade.Upgrade.test_dry_run_writes_nothing` | guard |
| 3.7.0 | An upgrade refuses tool code the project changed, so the tool never mixes two versions | `test_upgrade.Upgrade.test_refuses_modified_tool_code` | guard |
| 3.7.0 | An upgrade keeps the project's rules under "## Project rules" in AGENTS.md | `test_upgrade.Upgrade.test_merges_the_project_rules_section` | guard |
| 3.7.0 | An upgrade leaves .agents/hooks.json and docs/ as they are | `test_upgrade.Upgrade.test_keeps_hooks_json_and_docs` | guard |
| 3.7.0 | A second upgrade changes nothing | `test_upgrade.Upgrade.test_is_idempotent` | guard |
| 3.7.0 | An upgrade stopped by an error puts every file back; one stopped by a kill is put back byte for byte by --rollback | `test_upgrade.Upgrade.test_interrupted_then_rollback_restores_bytes` | guard |
| 3.7.0 | A rollback after sessions wrote needs --force and keeps their state | `test_upgrade.Upgrade.test_rollback_after_new_work_needs_force_and_keeps_the_state` | guard |
| 3.7.0 | A new tool that fails on the project is rolled back | `test_upgrade.Upgrade.test_a_new_tool_that_fails_on_the_project_is_rolled_back` | guard |
| 3.7.0 | A restore that fails exits 3 and names the rollback to run | `test_upgrade.Upgrade.test_a_failed_restore_exits_3_and_names_the_rollback` | guard |
| 3.7.0 | Both 3.6.6 manifest shapes, and a project without a manifest, upgrade correctly | `test_upgrade.Upgrade.test_bases_from_zip_and_head_manifests` | guard |
| 3.7.0 | An upgrade refuses a workspace a session owns | `test_upgrade.Upgrade.test_refuses_an_owned_workspace` | guard |
| 3.7.0 | An upgrade refuses a continuity.v2 workspace and names the migrate command | `test_upgrade.Upgrade.test_refuses_v2_and_names_migrate` | guard |
| 3.7.0 | An upgrade refuses a project whose .agents folder is a link | `test_upgrade.Upgrade.test_linked_agents_folder_is_refused` | guard |
| 3.7.0 | upgrade --scan lists the workspaces under a folder and writes nothing | `test_upgrade.Upgrade.test_scan_lists_versions_and_writes_nothing` | guard |
| 3.7.0 | A rebaseline cannot drop the entry of a project file, or of a file that still exists | `test_upgrade.Rebaseline.test_removed_entries_are_template_files_that_are_gone` | guard |
| 3.7.0 | Nothing told a session that the host it runs in had no hooks in the project, so new sessions started without the brief | `test_doctor.Doctor.test_missing_hooks_of_the_host_that_runs_it` | fails |
| 3.7.0 | Hooks that ran another folder's ws.py, as in a copied project, went unnoticed | `test_doctor.Doctor.test_hooks_that_run_another_projects_tool` | fails |
| 3.7.0 | Tool files that differ from the installed manifest, a mix of two versions, went unnoticed | `test_doctor.Doctor.test_tool_files_that_differ_from_the_manifest` | fails |
| 3.7.0 | ws doctor writes nothing and finds no problem in a sound project | `test_doctor.Doctor.test_a_healthy_project_has_no_problems_and_nothing_is_written` | guard |
| 3.7.0 | A rollback to 3.6.x did not say which evidence the older tool would refuse | `test_regressions.Evidence.test_13_evidence_rules_1_reads_differently_is_listed_for_a_rollback` | fails |
| 3.7.0 | The two-window tests failed under a Python whose folder is not on PATH, such as one installed by uv | `test_field.Windows.test_a_window_without_a_session_variable_cannot_claim_twice` | fails |
| 3.8.0 | A full stop after a path in Scope hid the path, so the task held the whole tree | `test_v38.Scope.test_17_a_full_stop_does_not_hide_the_path` | fails |
| 3.8.0 | Paths with letters outside ASCII were cut at the first such letter | `test_v38.Scope.test_17_paths_in_any_script` | fails |
| 3.8.0 | Any word in Scope was tried as a file name with .py added, so "login module" claimed login.py | `test_v38.Scope.test_17_words_are_not_turned_into_files` | fails |
| 3.8.0 | The "check:" prefix of an acceptance was read as check.py when such a file existed | `test_v38.Scope.test_17_the_check_prefix_is_not_a_path` | fails |
| 3.8.0 | Claims also took the paths of the acceptance command, so two tasks sharing a test could not run in parallel | `test_v38.Scope.test_17_claims_read_only_the_scope` | fails |
| 3.8.0 | Staleness reads the Scope paths plus the files the acceptance runs, including a unittest module and a pytest node | `test_v38.Scope.test_17_staleness_adds_the_files_the_acceptance_runs_and_claims_do_not` | fails |
| 3.8.0 | There was no way to name a file a task creates, a shared resource apart from paths, or the whole tree on purpose | `test_v38.Scope.test_17_new_resource_and_tree` | fails |
| 3.8.0 | A task whose Scope was prose naming no path was accepted and silently held the whole tree | `test_v38.Scope.test_17_add_refuses_prose_and_notes_a_planned_file` | fails |
| 3.8.0 | Rows written before that refusal are flagged, not refused | `test_v38.Scope.test_17_an_old_prose_scope_gets_a_hint_not_a_refusal` | fails |
| 3.8.0 | A sealed task whose files changed later stayed verified, and checkpoint and check --ready still said READY | `test_v38.Regression.test_18_a_change_after_sealing_names_the_task_and_the_file` | fails |
| 3.8.0 | There was no way to run every stale task again in one command | `test_v38.Regression.test_18_verify_stale_runs_the_acceptance_again` | fails |
| 3.8.0 | A project could not choose to be only warned about a regression after sealing | `test_v38.Regression.test_18_the_warn_setting_keeps_ready` | fails |
| 3.8.0 | The first session after an upgrade only warns about regressions found by the newer check; the next one is refused | `test_v38.Regression.test_18_the_first_session_after_an_upgrade_only_warns` | fails |
| 3.8.0 | The brief counted the requirements of a stale task as verified | `test_v38.Regression.test_18_the_verified_count_leaves_out_a_stale_task` | fails |
| 3.8.0 | A change inside a done task's scope counted as registered work even after it made that task's evidence stale | `test_v38.Regression.test_18_a_change_inside_a_stale_task_is_unregistered_work` | fails |
| 3.8.0 | Evidence of a task moved to CLOSED_ITEMS could be edited or deleted without notice | `test_v38.Regression.test_18_evidence_of_a_compacted_task_stays_sealed` | fails |
| 3.8.0 | A test weakened between a task's first run and its accepted one went unmentioned at the checkpoint | `test_v38.Delivery.test_19_a_test_weakened_after_a_failed_run_is_listed` | fails |
| 3.8.0 | A changed run command and a verify with --because went unmentioned at the checkpoint | `test_v38.Delivery.test_19_another_command_and_because_are_listed` | fails |
| 3.8.0 | A checkpoint did not say what the work rests on: the saved state, test or check evidence, and whether the host was tried | `test_v38.Delivery.test_21_a_checkpoint_states_what_the_delivery_rests_on` | fails |
| 3.8.0 | Coverage files written by a run, such as .coverage and coverage.xml, made the run rejected as a change to watched files | `test_v38.Runners.test_20_coverage_files_a_run_writes_do_not_reject_it` | fails |
| 3.8.0 | Output whose summary is not read was rejected without pointing to a report | `test_v38.Runners.test_20_unread_output_points_to_a_report` | fails |
| 3.8.0 | The brief showed only the last five retired rows, each cut to 50 characters | `test_v38.Prohibitions.test_u3_seven_retired_rows_all_appear` | fails |
| 3.8.0 | Past its size budget the brief gives the count of retired rows and the command that lists them all | `test_v38.Prohibitions.test_u3_past_the_budget_the_count_and_the_command_are_given` | fails |
| 3.8.0 | The brief showed only the first eight preferences | `test_v38.Prohibitions.test_u3_all_preferences_appear` | fails |
| 3.8.0 | ws add and ws set gave the agent no line to tell the user what was recorded | `test_v38.TurnRecord.test_x7_add_and_set_print_a_line_to_relay` | fails |
| 3.8.0 | The prompt hook did not say what the previous turn recorded, or that it recorded nothing | `test_v38.TurnRecord.test_x7_the_turn_hook_says_what_the_previous_turn_recorded` | fails |
| 3.8.0 | There was no view of user messages beside the rows or reasons that account for them | `test_v38.Review.test_x8_review_puts_each_message_beside_its_record` | fails |
| 3.8.0 | Six rules of the first contract had been deleted without the owner's agreement, and two needed new wording (owner decision D3) | `test_v38.Contract.test_29_the_contract_holds_the_restored_rules_in_no_more_bytes` | fails |
| 3.8.0 | The per-turn reminder did not carry the evidence rule, which compaction tends to drop | `test_v38.Contract.test_29_the_turn_reminder_carries_the_evidence_rule` | fails |
| 3.8.0 | The list of ways of working the owner ruled out stayed in the maintainer's files, so new projects never got it | `test_v38.Contract.test_29_a_new_project_lists_what_is_not_adopted` | fails |
| 3.8.0 | A message the user marked as discussion could still turn into numbered requirements, and ideas had no command | `test_v38.Modes.test_30_a_discussion_turn_gets_no_requirement_id` | fails |
| 3.8.0 | A message the user marked read-only did not stop ws writes in that turn | `test_v38.Modes.test_30_a_read_only_turn_writes_nothing` | fails |
| 3.8.0 | The prompt hook did not tell the agent that the user marked a message as a confirmation | `test_v38.Modes.test_30_a_confirmation_is_named` | fails |
| 3.9.0 | Python 3.9, the python3 that comes with macOS, was refused by the version gate (owner decision D0) | `test_regressions.Entry.test_x1_python_version_message` | fails |
| 3.9.0 | Upgrade and snapshot files were written with a keyword argument that Python 3.9 does not have | `test_static.SourceBytes.test_no_call_needs_a_python_newer_than_3_9` | fails |
| 3.9.0 | An empty lock file left by a command killed while writing it blocked every command for 60 seconds | `test_v39.Lock.test_22_an_empty_lock_file_from_a_crash_does_not_block` | fails |
| 3.9.0 | The READY check counted the lock of the process that ran it | `test_v39.Lock.test_22_the_ready_check_does_not_count_its_own_lock` | fails |
| 3.9.0 | A drive that cannot lock files gave no way out | `test_v39.Lock.test_22_a_drive_that_cannot_lock_names_the_way_out` | fails |
| 3.9.0 | A killed holder frees the system lock at once | `test_v39.Lock.test_22_a_killed_holder_frees_the_lock_at_once` | guard |
| 3.9.0 | WS_LOCK=legacy uses the lock file of 3.8 for this version | `test_v39.Lock.test_22_ws_lock_legacy_uses_the_older_lock_file` | guard |
| 3.9.0 | Eight concurrent writers lose and duplicate no row | `test_v39.Lock.test_22_eight_writers_get_unique_ids_and_lose_no_row` | guard |
| 3.9.0 | Who may run which write command was decided in five places; one table now decides it, and PROTOCOL prints that table | `test_v39.Permits.test_23_each_identity_may_run_what_the_table_says` | guard |
| 3.9.0 | The permission table in PROTOCOL could drift from the commands | `test_static.Process.test_protocol_prints_the_permission_table_the_commands_enforce` | guard |
| 3.9.0 | A parallel session could change or verify a task it had not claimed; its release left that task out, and the next main checkpoint stuck on it | `test_v39.Permits.test_23_p8_a_parallel_session_touches_only_tasks_in_its_claim` | fails |
| 3.9.0 | A parallel session could not drop its own task while the card named it: the status was refused, and so was the card | `test_v39.Permits.test_23_p8_a_dropped_task_leaves_the_card` | fails |
| 3.9.0 | Verify was rejected when another session edited files inside its own claim during the run | `test_v39.Permits.test_23_p7_verify_ignores_edits_inside_another_sessions_claim` | fails |
| 3.9.0 | A session that claimed with the --session key the hook prints lost that identity at the next write command, which did not accept --session | `test_v39.Permits.test_23_p6_a_session_key_tells_two_conversations_in_one_window_apart` | fails |
| 3.9.0 | Claude Code, Codex and Gemini saved a turn only in the Stop hook, after the checkpoint had released the workspace, so a READY workspace failed at once | `test_v39.Messages.test_24_ready_survives_the_stop_hook_that_copies_the_turn` | fails |
| 3.9.0 | A user message saved after the checkpoint overturned READY; it is now left to the next session | `test_v39.Messages.test_24_a_message_saved_after_the_seal_waits_for_the_next_session` | fails |
| 3.9.0 | The same sentence in two sessions had one message ID, so the second was never reconciled | `test_v39.Messages.test_24_the_same_sentence_in_two_sessions_is_reconciled_in_each` | fails |
| 3.9.0 | Reconcile rows of 3.8 stay valid when the transcript is written again | `test_v39.Messages.test_24_marks_of_3_8_stay_valid_when_the_transcript_is_written_again` | guard |
| 3.9.0 | A lone "no", "yes", "可以" or "行" was skipped as small talk, although it may answer a question | `test_v39.Messages.test_24_yes_and_no_are_reconciled_like_other_messages` | fails |
| 3.9.0 | A message ID was the hash of the redacted text, so the host's copy of a turn or a change of redaction rules reopened the message | `test_v39.Messages.test_24_the_stop_hook_keeps_the_id_when_the_host_copy_adds_to_the_typed_text` | fails |
| 3.9.0 | A transcript missing from INDEX.md was never read, while reconcile said every message was reconciled | `test_v39.Messages.test_24_a_transcript_missing_from_the_index_is_reported` | fails |
| 3.9.0 | One "ws reconcile all" closed every open message without naming how many | `test_v39.Messages.test_24_reconcile_all_names_how_many_it_marks` | fails |
| 3.9.0 | With the Stop nudge on, a turn that only answered a question was asked to record it | `test_v39.Messages.test_24_the_stop_nudge_lets_a_pure_question_pass` | fails |
| 3.9.0 | Only the BEGIN line of a private key was removed; its key lines stayed | `test_v39.Redaction.test_27_a_private_key_goes_as_one_block` | fails |
| 3.9.0 | Invisible characters were removed only from a line with no other credential, so a second one hidden by a soft hyphen stayed (appendix A6) | `test_v39.Redaction.test_27_invisible_characters_are_removed_before_matching_and_kept_elsewhere` | fails |
| 3.9.0 | JSON strings were redacted without their keys, so "password" and "secret_key" values stayed in the raw copy (appendix A6) | `test_v39.Redaction.test_27_a_json_key_says_its_string_is_the_secret` | fails |
| 3.9.0 | "账号admin 密码admin123", a password in a sentence, sshpass -p, mysql -p and a hex key after "api key" were kept | `test_v39.Redaction.test_27_chinese_labels_sentences_and_command_lines` | fails |
| 3.9.0 | "Password: minimum 8 characters", "Release key: v2.3.1-beta" and "S3 key: exports/2026/data.csv" were rewritten as [REDACTED] for good | `test_v39.Redaction.test_27_explanatory_text_is_left_alone` | fails |
| 3.9.0 | ws check did not scan the transcripts in docs/chats | `test_v39.Redaction.test_27_ws_check_scans_the_saved_transcripts` | fails |
| 3.9.0 | "plain" kept every credential as written everywhere, transcripts included; it now applies only to the files credential_files names (owner decision D2) | `test_v39.Redaction.test_27_d2_plain_keeps_credentials_only_in_the_files_the_owner_names` | fails |
| 3.9.0 | In ask mode a credential is redacted and no write is refused (owner decision D2) | `test_v39.Redaction.test_27_ask_mode_refuses_no_write` | guard |
| 3.9.0 | ws start copied every chat of the folder from nine host stores without asking, chats from before the setup included; it now waits for WORKSPACE "chat_import" (owner decision D1) | `test_v39.ChatImport.test_26_start_imports_nothing_until_the_user_decides` | fails |
| 3.9.0 | With import on, chats last written before init stay out | `test_v39.ChatImport.test_26_an_answer_at_init_imports_only_chats_from_after_the_setup` | fails |
| 3.9.0 | A git project was never asked whether docs/chats/ belongs in commits | `test_v39.ChatImport.test_26_a_git_project_is_asked_whether_git_ignores_the_chats` | fails |
| 3.9.0 | init --chats-git ignore adds docs/chats/ to the project's .gitignore, which an upgrade never replaces | `test_v39.ChatImport.test_26_ignore_adds_docs_chats_to_the_project_gitignore` | fails |
| 3.9.1 | 3.9.0 let a project whose WORKSPACE block says "on" import although the environment said WS_IMPORT=0; the environment decides for every project again, as the guides say | `test_v39.ChatImport.test_26_ws_import_in_the_environment_decides_for_every_project` | fails |
| 3.9.0 | A host that starts hooks in a subfolder could not find the relative ws.py; hooks enable --absolute writes quoted absolute paths that run from any folder, also under a path with spaces | `test_v39.HookPaths.test_25_absolute_hooks_run_from_a_subfolder_of_a_path_with_spaces` | fails |
| 3.9.0 | With --absolute, a PowerShell hook command gets the call operator & in front | `test_v39.HookPaths.test_25_powershell_commands_get_the_call_operator` | fails |
| 3.9.0 | Hook commands stay relative by default until the host trials decide (owner decision D5) | `test_v39.HookPaths.test_25_the_default_stays_relative` | guard |
| 3.9.0 | After an upgrade from 3.8, whose seal lists no open messages, every new message blocked READY until the next checkpoint; the upgrade now lists them as a seal does | `test_v39.Messages.test_24_an_upgrade_lists_the_open_messages_as_a_seal_does` | fails |
| 3.9.1 | An import judged a session by the date of its file, so a session that began before init and went on after it came in whole, older messages and raw copy included | `test_v39.ChatImport.test_26_a_session_that_began_before_the_setup_gives_only_its_later_messages` | fails |
| 3.9.1 | A session whose host stores no message time was imported whole; it is left out and named, and ws chats import HOST --all copies it when the user asks | `test_v39.ChatImport.test_26_a_session_without_message_times_is_left_out_and_named` | fails |
| 3.9.1 | The Windows launcher reported success for an invalid option and a failed readiness check | `test_v39.HookPaths.test_28_launchers_find_a_python_and_run_ws` | fails |
| 3.9.1 | A release built on Windows omitted the Unix launcher's execute permissions | `test_distribution.Install.test_export_writes_clean_zip` | fails |
| 3.9.1 | The handoff example kept an edit after a forced takeover and tried to finish with stale evidence | `test_distribution.Install.test_minimal_cycle_completes_the_handoff` | fails |
| 3.9.1 | A changed customer guide under docs still counted as verified after a checkpoint | `test_v38.Regression.test_document_edits_invalidate_the_delivered_guide` | fails |
| 3.9.1 | Folder additions and deletions, shared runs and evidence recorded before document hashes | `test_v38.Regression.test_document_folder_grouped_proof_and_legacy_evidence` | guard |
| 3.9.1 | Redaction removed algorithm names, command options, paths and numeric counts after a credential label | `test_v39.Redaction.test_27_a_path_an_algorithm_or_an_option_after_a_label_is_left_alone` | fails |
| 3.9.1 | Distinguish a token count from a short numeric password and preserve password masking in both chat copies | `test_v39.Redaction.test_literal_passwords_are_kept_private_in_both_chat_copies` | guard |
| 3.9.1 | An upgrade rollback restores the previous launcher and its Unix execute permissions | `test_upgrade.Upgrade.test_rollback_restores_the_previous_launcher` | guard |
| 3.9.2 | Changing a compacted task left READY and verified coverage green | `test_quality.Verification.test_archived_task_can_be_reverified_without_rewriting_history` | fails |
| 3.9.2 | A later failing acceptance left the earlier pass current | `test_quality.Verification.test_later_failure_invalidates_the_old_pass_with_unchanged_files` | fails |
| 3.9.2 | A single passing task hid another stale task for the same requirement | `test_quality.Verification.test_all_tasks_of_one_requirement_must_be_current` | fails |
| 3.9.2 | Pruning could delete a referenced JSON report and the previous task proof | `test_quality.Verification.test_prune_keeps_the_report_attachment_and_previous_task_runs` | fails |
| 3.9.2 | The old accepted row hid a later rejected run after an upgrade | `test_quality.Verification.test_upgrade_recovers_a_later_legacy_rejection` | guard |
| 3.9.2 | An archived task can be retried only with its recorded definition | `test_quality.Verification.test_reverification_checks_the_original_archived_definition` | guard |
| 3.9.2 | Codex answers disappeared and private host records reached the second transcript copy | `test_quality.VisibleConversation.test_only_visible_messages_and_question_answers_reach_both_copies` | fails |
| 3.9.2 | An older export erased the last hook correction | `test_quality.VisibleConversation.test_lagging_snapshot_keeps_the_last_correction_and_indexes_the_real_count` | fails |
| 3.9.2 | Two equal turns were collapsed and an edited instruction reused the old ID | `test_quality.VisibleConversation.test_equal_turns_and_an_edited_instruction_keep_distinct_identities` | fails |
| 3.9.2 | A local trial filename certified a handoff without a result | `test_quality.VisibleConversation.test_trial_filename_does_not_certify_a_handoff` | fails |
| 3.9.2 | A substantive extension inherited the reconciliation of shorter text | `test_quality.VisibleConversation.test_a_substantive_extension_needs_a_fresh_reconciliation` | fails |
| 3.9.2 | A repeated final answer after a new question was omitted | `test_quality.VisibleConversation.test_repeated_reply_after_a_new_question_is_saved` | fails |
| 3.9.2 | A second task could mark a feature shipped while its first task had stale evidence | `test_quality.Verification.test_feature_waits_for_all_of_its_product_evidence` | fails |
| 3.9.2 | Identical turns can be distinguished by their native IDs when the host inserts an earlier turn | `test_quality.VisibleConversation.test_host_ids_distinguish_equal_turns_after_insertion` | guard |
| 3.9.2 | The desktop UI recorded a visible question absent from the model stream and an attachment occurred in both | `test_quality.VisibleConversation.test_desktop_visible_only_question_and_dual_stream_attachments` | fails |
| 3.9.2 | An explicit rewind of a previously observed host export retires a turn while retaining its earlier visible revision | `test_quality.VisibleConversation.test_explicit_host_rewind_keeps_removed_turns_in_history_only` | guard |
| 3.9.3 | A sealed next step still appeared current after a later decision | `test_handover.Handoff.test_new_decision_displaces_old_step_and_links_message` | fails |
| 3.9.3 | The handoff gave an old observation without an expiry | `test_handover.Handoff.test_unlinked_decision_in_legacy_seal_and_expired_observation` | fails |
| 3.9.3 | A stopped batch needed a separate manual handover to recover its remaining work | `test_handover.Handoff.test_recover_only_remaining_batch_in_a_new_session` | fails |
| 3.9.3 | Accepted tests could accompany different delivery bytes | `test_handover.Delivery.test_green_tests_do_not_verify_a_different_delivery` | fails |
| 3.9.3 | A receipt could not identify the approved member inside an envelope | `test_handover.Delivery.test_trusted_digest_member_and_multiple_scopes` | fails |
| 3.9.3 | An acceptance command could change the file during the check | `test_handover.Delivery.test_receipt_checked_after_the_command_as_well` | fails |
| 3.9.3 | The compatible hook mixed host envelopes with user decisions | `test_handover.Conversation.test_source_routes_envelopes_and_preserves_two_equal_user_turns` | fails |
| 3.9.3 | A provider-prefixed key remained in both chat copies | `test_handover.Conversation.test_chat_policy_redacts_both_copies_revisions_and_snapshot` | fails |
| 3.9.3 | Live chat writes had no independent project control | `test_handover.Conversation.test_live_capture_can_be_disabled_independently_of_import` | fails |
| 3.9.3 | An approved artifact could be bundled with a credential in another ZIP member | `test_handover.Delivery.test_nested_delivery_preflight_catches_credentials_before_copy` | fails |
| 3.9.3 | A final receipt left its settled risk on the handoff card | `test_handover.Delivery.test_final_receipt_closes_only_the_recorded_risk` | fails |
| 3.9.3 | A locally edited template could export a provider key to a folder and ZIP | `test_handover.Delivery.test_export_checks_the_actual_template_before_creating_either_copy` | fails |
| 3.9.4 | A checkpoint could release an obsolete step as READY after the scope changed | `test_handover.Handoff.test_sealed_step_needs_review_after_the_user_withdraws_approval` | fails |
| 3.9.4 | A decision with a higher ID displaced a recently revised decision in the brief | `test_handover.Handoff.test_latest_decision_follows_the_last_real_edit_over_seals_and_replays` | fails |
| 3.9.4 | Updating a batch dropped its previous evidence and artifact references | `test_handover.Handoff.test_batch_references_survive_updates_and_history_is_idempotent` | fails |
| 3.9.4 | A recent decision edit may live in the archived change log | `test_handover.Handoff.test_latest_decision_uses_the_verified_archived_change_log` | guard |
