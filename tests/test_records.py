"""Unit: records hold exactly the SSoT §5 vocabulary. Runs green now."""

import dataclasses

import pytest

from dibs.records import Agent, EventKind, Status


def test_status_values_are_db_strings():
    """SSoT §5: tasks.status stores these literal strings."""
    expected = ('todo', 'doing', 'done', 'orphaned')
    assert tuple(status.value for status in Status) == expected


def test_event_kinds_match_ssot():
    """SSoT §5: events.kind holds exactly these literals, in order."""
    expected = (
        'init', 'sync', 'join', 'claim', 'done', 'drop', 'note', 'reap',
        'orphan',
    )
    assert tuple(kind.value for kind in EventKind) == expected


def test_rows_are_frozen():
    """ARCHITECTURE §1: data is immutable; behavior lives in modules."""
    agent = Agent(agent_id='brave-otter-1111', name='brave-otter')
    with pytest.raises(dataclasses.FrozenInstanceError):
        agent.name = 'other'  # type: ignore[misc]
