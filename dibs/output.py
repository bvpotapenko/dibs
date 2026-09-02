"""Every user-facing string and terseness cap lives here (C5, D14).

Output is prompt surface: terse, steering, self-sufficient (I10); in an
8k window every dibs token competes with code. Level L1 (imports L0;
the guarded planfile import is a type-only sibling edge, ARCHITECTURE
§4). Member budget 5 (ARCHITECTURE §3).
"""

from typing import TYPE_CHECKING

from dibs.records import Event
from dibs.runtime import DibsError, Reply

if TYPE_CHECKING:
    from dibs.planfile import PlanItem

EVENT_CAP = 15  # SSoT §13: unseen events shown before '... and N more'


def render_reply(reply: Reply) -> str:
    """Join result lines, capped one-line events, then the hint (D14).

    Overflow past EVENT_CAP collapses to '... and N more - run
    `dibs list`' (SSoT §13). No banners, ever.
    """
    raise NotImplementedError('ARCHITECTURE §13 step 7: render_reply')


def render_error(err: DibsError) -> str:
    """Format '<message>' with 'Run: <steer>' as the last line (I10)."""
    raise NotImplementedError('ARCHITECTURE §13 step 7: render_error')


def format_event(event: Event) -> str:
    """Compress one event to one line, worker-readable alone (D10, D14)."""
    raise NotImplementedError('ARCHITECTURE §13 step 7: format_event')


def next_hint(verb: str, context_bits: dict[str, str]) -> str:
    """Look up the next-expected-verb line, exact syntax included (D14)."""
    raise NotImplementedError('ARCHITECTURE §13 step 7: next_hint')


def format_preview(plan_items: 'tuple[PlanItem, ...]') -> tuple[str, ...]:
    """Render the verify view: tree with waits-for, would-be IDs (D21).

    Sections, titles, body presence, hand-written [x], plus inline
    warnings (bodiless tasks, duplicate titles) are computed here, not
    in verbs (C5, C6, D22).
    """
    raise NotImplementedError('ARCHITECTURE §13 step 7: format_preview')
