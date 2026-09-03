"""Identity and board-key minting (SSoT §7, D8, D20).

Level L3: may use transitions.register_agent for the mint-retry loop.
Member budget 2 (ARCHITECTURE §3). Implementation note: prefer
secrets.choice / secrets.token_hex over random - not for security
(D8/D20 stay honest about that) but to keep bandit S311 silent without
a suppression.
"""

import secrets
from sqlite3 import Connection

from dibs import transitions
from dibs.records import Agent

ID_DIGITS = 4  # numeric suffix width in 'name-NNNN' ids (SSoT §7)
ID_SPACE = 10 ** ID_DIGITS  # suffixes 0000..9999
KEY_GROUP_BYTES = 2  # two hex chars per byte: 'dibs-7f3a-9c2e' (SSoT §13)

ADJECTIVES = (
    'agile', 'amber', 'bold', 'brave', 'breezy', 'bright', 'brisk',
    'calm', 'candid', 'cheery', 'civil', 'clever', 'crisp', 'daring',
    'deft', 'eager', 'earnest', 'fleet', 'frank', 'gentle', 'glad',
    'golden', 'grand', 'happy', 'hardy', 'hearty', 'humble', 'jaunty',
    'jolly', 'keen', 'kind', 'lively', 'loyal', 'lucid', 'lucky',
    'mellow', 'merry', 'mild', 'nimble', 'noble', 'perky', 'plucky',
    'polite', 'proud', 'quick', 'quiet', 'ready', 'steady', 'sunny',
    'trusty',
)

ANIMALS = (
    'badger', 'beaver', 'bison', 'bobcat', 'camel', 'condor', 'crane',
    'dingo', 'dolphin', 'donkey', 'eagle', 'egret', 'elephant',
    'falcon', 'ferret', 'finch', 'fox', 'gazelle', 'gecko', 'gibbon',
    'heron', 'ibex', 'jaguar', 'kestrel', 'kiwi', 'koala', 'lemur',
    'llama', 'lynx', 'magpie', 'marmot', 'meerkat', 'moose', 'ocelot',
    'orca', 'osprey', 'otter', 'owl', 'panda', 'pelican', 'penguin',
    'plover', 'puffin', 'quokka', 'raven', 'robin', 'seal', 'tapir',
    'wombat', 'wren',
)


def mint_identity(conn: Connection, now: int) -> Agent:
    """Pick adjective-animal-NNNN, retrying register_agent on UNIQUE (I1).

    `now` stamps the join event - one clock per invocation (I6).

    Name for display, id for command input (D8, I7); scope is this
    board only (SSoT §7). secrets, not random, only to keep bandit
    quiet - confusion resistance is not security (D8).
    """
    while True:
        name = f'{secrets.choice(ADJECTIVES)}-{secrets.choice(ANIMALS)}'
        digits = str(secrets.randbelow(ID_SPACE)).zfill(ID_DIGITS)
        agent = Agent(agent_id=f'{name}-{digits}', name=name)
        if transitions.register_agent(conn, agent, now):
            return agent


def mint_board_key() -> str:
    """Mint 'dibs-' + 8 random hex chars in two groups (D20, SSoT §13).

    The dibs- prefix makes every handoff line its own skill trigger
    (D20); truth lives in meta.board_key, the registry is a cache.
    """
    head = secrets.token_hex(KEY_GROUP_BYTES)
    tail = secrets.token_hex(KEY_GROUP_BYTES)
    return f'dibs-{head}-{tail}'
