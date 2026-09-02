"""Unit: the SSoT §8 recognition table, annotation grammar, sync diff.

Pure functions only - no fixtures beyond plan_text (C4 makes this tier
trivial to test; keep it that way).
"""


def test_parse_recognizes_three_checkbox_forms(plan_text):
    """§8: '- [ ]', '- [x]', '- [~ name]' are tasks; states captured."""
    raise NotImplementedError('needs parse_plan (§13 step 3)')


def test_parse_attaches_indented_prose_as_body(plan_text):
    """§8: indented non-checkbox lines travel with the task as body."""
    raise NotImplementedError('needs parse_plan (§13 step 3)')


def test_parse_nested_checkbox_is_child(plan_text):
    """D22: an indented checkbox's parent_line is the nearest
    less-indented checkbox above it, not just any previous line."""
    raise NotImplementedError('needs parse_plan (§13 step 3)')


def test_parse_nesting_depth_is_free():
    """D22: three-plus levels parse; each child gates only its parent."""
    raise NotImplementedError('needs parse_plan (§13 step 3)')


def test_parse_deep_prose_stays_body(plan_text):
    """D22/§11: prose indented deeper than a child is body, not a task."""
    raise NotImplementedError('needs parse_plan (§13 step 3)')


def test_parse_sections_letter_in_order(plan_text):
    """§8: nearest heading is the section; lettered A, B in doc order."""
    raise NotImplementedError('needs parse_plan (§13 step 3)')


def test_parse_no_headings_single_section():
    """§8: a plan with no headings gets one implicit section."""
    raise NotImplementedError('needs parse_plan (§13 step 3)')


def test_parse_ignores_plain_bullets_and_prose(plan_text):
    """§8: plain bullets, numbered lines, prose are never tasks."""
    raise NotImplementedError('needs parse_plan (§13 step 3)')


def test_parse_fence_lookalike_policy():
    """Open point: a literal '- [ ]' inside a code fence matches the §8
    line rule. Decide (probably: line rule wins, documented), pin the
    behavior here, and note the decision in SSoT §8 if it deviates."""
    raise NotImplementedError('needs parse_plan (§13 step 3)')


def test_annotate_rewrites_only_grammar_lines(plan_text):
    """I4: every byte outside annotation-grammar lines is preserved."""
    raise NotImplementedError('needs annotate_lines (§13 step 3)')


def test_annotate_todo_doing_done_forms():
    """§8 grammar: '- [ ] t', '- [~ name] t', '- [x] t  ✓ name: note'."""
    raise NotImplementedError('needs annotate_lines (§13 step 3)')


def test_annotate_is_idempotent(plan_text):
    """I4: annotating an already-annotated text changes nothing."""
    raise NotImplementedError('needs annotate_lines (§13 step 3)')


def test_hash_normalizes_case_and_spaces():
    """§8: title_hash('A  B') == title_hash('a b'); stable otherwise."""
    raise NotImplementedError('needs title_hash (§13 step 3)')


def test_hash_excludes_done_annotation():
    """§8: the '✓ name: note' suffix never feeds the title hash."""
    raise NotImplementedError('needs parse_plan + title_hash (§13.3)')


def test_sync_new_line_becomes_task(plan_text):
    """§8 sync: a new checkbox line lands in SyncPlan.new."""
    raise NotImplementedError('needs compute_sync (§13 step 3)')


def test_sync_vanished_line_orphaned(plan_text):
    """§8 sync + I5: a removed line is orphaned, never deleted."""
    raise NotImplementedError('needs compute_sync (§13 step 3)')


def test_sync_hand_checked_imports_done(plan_text):
    """§8 sync: [x] over todo lands in SyncPlan.checked (owner human)."""
    raise NotImplementedError('needs compute_sync (§13 step 3)')


def test_sync_reorder_updates_seq_only(plan_text):
    """§8 sync + I5/D7: reordering changes seq; IDs stay untouched."""
    raise NotImplementedError('needs compute_sync (§13 step 3)')


def test_sync_reindent_updates_parent(plan_text):
    """§8 sync + D22: re-indenting under another checkbox moves
    parent_id (and back to None at top level); ID untouched."""
    raise NotImplementedError('needs compute_sync (§13 step 3)')


def test_sync_regressed_checkbox_flagged(plan_text):
    """§8 sync: [ ] over doing/done lands in regressed; DB wins."""
    raise NotImplementedError('needs compute_sync (§13 step 3)')


def test_sync_retitle_is_vanish_plus_new(plan_text):
    """§8 sync: an edited title orphans the old task and adds a new
    one; both flagged (accepted v1 limitation)."""
    raise NotImplementedError('needs compute_sync (§13 step 3)')


def test_sync_duplicate_titles_match_in_order():
    """§8 sync: identical titles pair up by document order."""
    raise NotImplementedError('needs compute_sync (§13 step 3)')
