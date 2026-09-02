"""Unit: rendering, caps, hints, steers (C5, D14, I10; §13 step 7).

Feed hand-built records/Reply values; no DB, no board fixture needed.
"""

from dibs import output, planfile
from dibs.records import Event, EventKind
from dibs.runtime import DibsError, Reply

NOW = 1_700_000_000  # fixed clock; nothing here reads a real one
OTTER = 'brave-otter-1111'
ELEPHANT = 'happy-elephant-2222'
OVERFLOWING = output.EVENT_CAP + 5  # enough events to trip the cap
HINT = 'Next: dibs done A2 --note "what changed"'

# Two tasks share a title, and the second has no body: one document
# exercising both inline warnings (D21).
DUPE_PLAN = """## Chores

- [ ] Water the plants
  Every pot on the balcony.
- [ ] Water the plants
"""


def event(kind, task_id=None, text='', to_agent=None, agent=OTTER):
    """One journal row, shaped as the DB hands it back."""
    return Event(1, NOW, agent, kind, task_id, to_agent, text)


def preview_of(text):
    """The verify view for a plan document."""
    return output.format_preview(planfile.parse_plan(text))


def row_for(lines, task_id):
    """The single preview line whose would-be ID is task_id."""
    return next(
        line for line in lines
        if line.strip().split('  ')[0] == task_id
    )


def test_render_reply_lines_events_hint_order():
    """D14: result lines, then events one per line, hint last."""
    reply = Reply(
        lines=('you are happy-elephant', 'claimed A2: Ship it'),
        events=(event(EventKind.DONE, 'A1', 'anchored the regex'),),
        hint=HINT,
    )

    rendered = output.render_reply(reply).split('\n')

    assert rendered == [
        'you are happy-elephant',
        'claimed A2: Ship it',
        output.EVENTS_HEADER,
        'done A1 by brave-otter: "anchored the regex"',
        HINT,
    ]
    # No feed at all when nothing is unseen: no empty banner (D14).
    assert output.render_reply(
        Reply(lines=('ok',), events=(), hint=HINT),
    ).split('\n') == ['ok', HINT]


def test_events_capped_with_overflow_hint():
    """SSoT §13: more than EVENT_CAP unseen events collapse into
    '... and N more' pointing at `dibs list`."""
    reply = Reply(
        lines=(),
        events=tuple(
            event(EventKind.NOTE, text='chatter')
            for _each in range(OVERFLOWING)
        ),
        hint=HINT,
    )

    rendered = output.render_reply(reply).split('\n')

    # header + EVENT_CAP events + overflow + hint
    assert len(rendered) == output.EVENT_CAP + 3
    assert rendered.count('note by brave-otter: "chatter"') == (
        output.EVENT_CAP
    )
    assert rendered[-2] == output.OVERFLOW.format(
        OVERFLOWING - output.EVENT_CAP,
    )
    assert 'dibs list' in rendered[-2]


def test_render_error_ends_with_run_steer():
    """I10: render_error output ends with 'Run: <steer>' verbatim."""
    rendered = output.render_error(
        DibsError(output.NOT_OWNER.format('A2'), output.RECLAIM.format('A2')),
    )

    assert rendered.startswith('A2 is not yours')
    assert rendered.split('\n')[-1] == 'Run: dibs claim --task A2'


def test_format_event_is_one_line():
    """D14: every EventKind formats to exactly one line, no banners."""
    every = tuple(
        event(kind, 'A1', 'a note\nwith a newline in it')
        for kind in EventKind
    )

    assert all('\n' not in output.format_event(one) for one in every)
    # I7: shared surfaces show names, never session ids.
    assert all(OTTER not in output.format_event(one) for one in every)
    assert all('brave-otter' in output.format_event(one) for one in every)
    assert output.format_event(
        event(EventKind.NOTE, text='yours', to_agent=ELEPHANT),
    ) == 'note by brave-otter to happy-elephant: "yours"'
    assert output.format_event(
        event(EventKind.REAP, 'A1', 'Fix the tokenizer'),
    ) == 'reap A1 from brave-otter: "Fix the tokenizer"'


def test_next_hint_has_exact_syntax():
    """D14: hints carry runnable syntax (e.g. `dibs done A2 --note
    "..."`), not descriptions of it."""
    assert output.next_hint('claim', {'task': 'A2'}) == HINT
    assert output.next_hint('done', {}) == 'Next: dibs claim'
    assert output.next_hint('init', {'key': 'dibs-7f3a-9c2e'}) == (
        'Hand each session: /dibs dibs-7f3a-9c2e'
    )
    # A verb that omits a slot still emits a runnable shape, never a
    # KeyError (I10).
    assert 'dibs done <ID>' in output.next_hint('claim', {})


def test_preview_shows_tree_and_waits_for(plan_text):
    """D21/D22: format_preview renders sections, would-be IDs, the
    nesting tree, and what each parent waits for."""
    lines = preview_of(plan_text)

    assert lines[0] == 'sections: A Parser, B Docs'
    assert tuple(
        line.strip().split('  ')[0] for line in lines[1:]
    ) == ('A1', 'A2', 'A2.1', 'A2.2', 'A3', 'B1')
    # Nesting is the indent; gating is the derived waits-for (D22).
    assert (
        row_for(lines, 'A2.1').startswith(output.TREE_STEP),
        row_for(lines, 'A2').startswith(output.TREE_STEP),
    ) == (True, False)
    assert (
        row_for(lines, 'A2').endswith('waits for A2.1, A2.2'),
        'waits for' in row_for(lines, 'A1'),
    ) == (True, False)
    # The author's own [x] shows as written, and never as a task dibs
    # is waiting on.
    assert '[x] Rename Lexer to Tokenizer' in row_for(lines, 'A3')


def test_preview_letters_an_unheaded_plan():
    """SSoT §8: no headings means one implicit, nameless section - it
    still gets its letter, and the IDs still start at A1."""
    lines = preview_of('- [ ] Buy milk\n  From the corner shop.\n')

    assert lines == ('sections: A', 'A1  Buy milk')


def test_preview_warns_bodiless_and_dupes(plan_text):
    """D21: bodiless tasks and duplicate titles get inline warnings -
    computed here, not in verbs (C5/C6). PLAN_TEXT's 'Cover the empty
    file' child is the bodiless case."""
    lines = preview_of(plan_text)
    dupes = preview_of(DUPE_PLAN)

    assert (
        output.NO_BODY in row_for(lines, 'A2.2'),
        output.NO_BODY in row_for(lines, 'A2.1'),
    ) == (True, False)
    assert output.DUPLICATE not in ''.join(lines)
    # Both halves of a duplicate pair are flagged, not just the second.
    assert output.DUPLICATE in row_for(dupes, 'A1')
    assert output.DUPLICATE in row_for(dupes, 'A2')
    assert output.NO_BODY in row_for(dupes, 'A2')
