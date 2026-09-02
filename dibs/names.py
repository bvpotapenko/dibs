"""Identity and board-key minting (SSoT §7, D8, D20).

Level L3: may use transitions.register_agent for the mint-retry loop.
Member budget 2 (ARCHITECTURE §3). Implementation note: prefer
secrets.choice / secrets.token_hex over random - not for security
(D8/D20 stay honest about that) but to keep bandit S311 silent without
a suppression.
"""

from secrets import choice, randbelow, token_hex
from sqlite3 import Connection

from dibs import transitions
from dibs.records import Agent

ID_DIGITS = 4  # numeric suffix width in 'name-NNNN' ids (SSoT §7)
ID_CEILING = 10 ** ID_DIGITS  # exclusive bound on the numeric suffix
KEY_BYTES = 4  # token_hex(4) -> the 8 hex chars of a board key (D20)
KEY_GROUP = 4  # ... split into two dash-separated groups (SSoT §13)

# Both joins in one template: 'brave' + 'otter' -> 'brave-otter', then
# 'brave-otter' + '1111' -> the id. Name displays, id addresses (I7).
JOINED = '{0}-{1}'
BOARD_KEY = 'dibs-{0}-{1}'  # the dibs- prefix is a skill trigger (D20)

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


def mint_identity(conn: Connection) -> Agent:
    """Pick adjective-animal-NNNN, retrying register_agent on UNIQUE (I1).

    Name for display, id for command input (D8, I7); scope is this
    board only (SSoT §7).
    """
    taken = True
    while taken:
        name = JOINED.format(choice(ADJECTIVES), choice(ANIMALS))
        digits = str(randbelow(ID_CEILING)).zfill(ID_DIGITS)
        agent = Agent(JOINED.format(name, digits), name)
        # The UNIQUE name is the whole check: re-roll on a lost insert,
        # never look before inserting (I1).
        taken = not transitions.register_agent(conn, agent)
    return agent


def mint_board_key() -> str:
    """Mint 'dibs-' + 8 random hex chars in two groups (D20, SSoT §13).

    The dibs- prefix makes every handoff line its own skill trigger
    (D20); truth lives in meta.board_key, the registry is a cache.
    """
    hexes = token_hex(KEY_BYTES)
    return BOARD_KEY.format(hexes[:KEY_GROUP], hexes[KEY_GROUP:])
