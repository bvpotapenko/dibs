"""Integration: author-side writes on a tmp WAL DB (§11, §13 step 7).

From this step on tests/boards.build_board seeds through found_board +
apply_sync and its raw INSERT is deleted (ARCHITECTURE §11).
"""


def test_found_board_wins_once(board):
    """I1/D20: first call True + INIT event; second call False, no event,
    key unchanged; max_hand stamped from the argument (D6)."""
    raise NotImplementedError('needs plansync.found_board (§13 step 7)')


def test_apply_sync_empty_board_is_init(tmp_path, plan_text):
    """D24: on an empty board every line is new; rows land with minted ids
    in seq order, a hand [x] imports as done by 'human' with one DONE
    event, one SYNC event follows, plan_mtime is stamped."""
    raise NotImplementedError('needs plansync.apply_sync (§13 step 7)')


def test_apply_sync_same_text_only_journals(board):
    """§8 idempotence: a second apply_sync on unchanged text changes no
    row and appends exactly one SYNC event (C3)."""
    raise NotImplementedError('needs plansync.apply_sync (§13 step 7)')


def test_apply_sync_refreshes_cached_text_only(board, two_agents):
    """D4/C11: reword a body, rename a heading, re-indent, reorder while a
    task is doing -> body/section/parent_id/seq refreshed, status/owner/
    claimed_at untouched, id unchanged."""
    raise NotImplementedError('needs plansync.apply_sync (§13 step 7)')


def test_apply_sync_orphans_and_reserves_ids(board):
    """I5: a removed line -> orphaned (never deleted); a new line in that
    section takes the NEXT ordinal, never the orphan's."""
    raise NotImplementedError('needs plansync.apply_sync (§13 step 7)')


def test_apply_sync_converges_under_contention(board):
    """C11: two connections apply the same edit; BEGIN IMMEDIATE serializes
    them and the second finds nothing new - one row set, no duplicate
    ids, two SYNC events."""
    raise NotImplementedError('needs plansync.apply_sync (§13 step 7)')
