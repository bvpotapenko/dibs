"""Unit: runtime plumbing carries exactly the ARCHITECTURE §5 contract.

Runs green now (types landed with the skeleton, ARCHITECTURE §13 step 1).
"""

import dataclasses
import sqlite3
from contextlib import closing

import pytest

from dibs.runtime import Context, DibsError, Reply


def test_dibs_error_keeps_message_and_steer():
    """C7/I10: one error type, two channels; str() is the message alone."""
    err = DibsError('Unknown task B7', 'dibs claim --task A7')
    assert err.message == 'Unknown task B7'
    assert err.steer == 'dibs claim --task A7'
    assert str(err) == 'Unknown task B7'
    assert DibsError.__bases__ == (Exception,)
    assert DibsError.__subclasses__() == []


def test_context_fields_match_architecture(tmp_path):
    """ARCHITECTURE §5: conn, plan_path, db_path, actor, now; frozen (C8)."""
    expected = ('conn', 'plan_path', 'db_path', 'actor', 'now')
    names = tuple(field.name for field in dataclasses.fields(Context))
    assert names == expected
    db_path = tmp_path / '.plan.md.dibs'
    with closing(sqlite3.connect(db_path)) as conn:
        ctx = Context(conn, tmp_path / 'plan.md', db_path, None, 1_700_000_000)
        with pytest.raises(dataclasses.FrozenInstanceError):
            ctx.actor = 'brave-otter-1111'  # type: ignore[misc]


def test_reply_fields_match_architecture():
    """ARCHITECTURE §5: Reply = lines, events, hint; frozen (C8)."""
    names = tuple(field.name for field in dataclasses.fields(Reply))
    assert names == ('lines', 'events', 'hint')
    reply = Reply(lines=('claimed A1',), events=(), hint='dibs done A1')
    with pytest.raises(dataclasses.FrozenInstanceError):
        reply.hint = 'other'  # type: ignore[misc]
