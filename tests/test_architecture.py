"""Architecture guard: the budgets are a test, not a hope (§13 step 15).

SSoT §2 (size), ARCHITECTURE §3 (member budgets) and §4 (layering) are
held here as one table each. A number changes only together with the
document it mirrors: a red case here is a design drift, never a test
to edit alone. AST + tokenize over dibs/, no imports of the package.
Six measurement helpers, one per noun (§13 step 15): a module's member
count, its import edges, the §4 key an alias resolves to, the rows
tokens touch, the rows docstrings occupy, and the SSoT §2 code lines.
"""

import ast
import tokenize
from pathlib import Path
from types import MappingProxyType

ROOT = Path(__file__).resolve().parent.parent  # the repo, never the CWD
PACKAGE = ROOT / 'dibs'
HARD_STOP = 1700  # SSoT §2: code lines, counted as §2 defines them
FILE_CAP = 18  # SSoT §2: .py files under dibs/
# §3 counts these and nothing else; constants are free
MEMBER_NODES = (ast.FunctionDef, ast.ClassDef)
# the nodes that can carry a docstring (ast.get_docstring's domain)
DOC_NODES = (ast.Module, ast.ClassDef, ast.FunctionDef)
# tokens that carry no code: a row touched only by these is not a code line
SKIPPED_TOKENS = frozenset((
    tokenize.COMMENT,
    tokenize.NL,
    tokenize.NEWLINE,
    tokenize.INDENT,
    tokenize.DEDENT,
    tokenize.ENCODING,
    tokenize.ENDMARKER,
))
# ARCHITECTURE §3: module -> member budget (top-level defs + classes)
MEMBER_BUDGETS = MappingProxyType({
    'dibs/__init__.py': 0,
    'dibs/__main__.py': 0,
    'dibs/runtime.py': 3,
    'dibs/records.py': 7,
    'dibs/store.py': 4,
    'dibs/planfile.py': 7,
    'dibs/output.py': 6,
    'dibs/views.py': 3,
    'dibs/trace.py': 3,
    'dibs/transitions.py': 6,
    'dibs/queries.py': 7,
    'dibs/plansync.py': 2,
    'dibs/names.py': 2,
    'dibs/cli.py': 6,
    'dibs/verbs/__init__.py': 0,
    'dibs/verbs/work.py': 4,
    'dibs/verbs/board.py': 5,
})
# ARCHITECTURE §4: module -> level; a module imports strictly lower ones.
# __main__ is L6 (Rev 12): the entry stub imports cli, which is L5.
LEVELS = MappingProxyType({
    'runtime': 0,
    'records': 0,
    'store': 1,
    'planfile': 1,
    'output': 1,
    'views': 1,
    'trace': 1,
    'transitions': 2,
    'queries': 2,
    'names': 3,
    'plansync': 3,
    'verbs': 4,
    'cli': 5,
    '__main__': 6,
})


def members_of(path: Path) -> int:
    """Top-level functions and classes in a module; constants are free (§3).

    MEMBER_NODES over ast.parse(path.read_text()).body, nothing deeper.
    """
    raise NotImplementedError('ARCHITECTURE §13 step 15: members_of')


def import_edges(path: Path) -> tuple[tuple[str, str], ...]:
    """(importer, imported) §4 keys for every top-level `from dibs… import`.

    Importer key: path.relative_to(PACKAGE).with_suffix('').parts[0], so
    verbs/work.py is `verbs`. tree.body only: a TYPE_CHECKING block is an
    If there and is skipped by position. Bind the ImportFrom nodes first,
    then one two-`for` comprehension over them, filtered on
    node.module.startswith(PACKAGE.name), and their aliases (WPS224/307).
    """
    raise NotImplementedError('ARCHITECTURE §13 step 15: import_edges')


def imported_key(node: ast.ImportFrom, alias: ast.alias) -> str:
    """The §4 key one alias resolves to.

    (node.module.partition('.')[2] or alias.name).partition('.')[0]:
    `from dibs import output` -> output, `from dibs.records import Task`
    -> records, `from dibs.verbs import board` -> verbs.
    """
    raise NotImplementedError('ARCHITECTURE §13 step 15: imported_key')


def token_lines(source: str) -> set[int]:
    """Rows a code token touches (SSoT §2).

    tokenize.generate_tokens over the source; every token not in
    SKIPPED_TOKENS adds range(start[0], end[0] + 1), so a multi-line
    STRING - a SQL or template body - spans all its rows.
    """
    raise NotImplementedError('ARCHITECTURE §13 step 15: token_lines')


def docstring_lines(tree: ast.Module) -> set[int]:
    """Rows every docstring occupies.

    ast.walk; for a DOC_NODES node whose ast.get_docstring is not None,
    the rows of node.body[0] (lineno..end_lineno).
    """
    raise NotImplementedError('ARCHITECTURE §13 step 15: docstring_lines')


def code_lines(path: Path) -> int:
    """SSoT §2 code lines of one module.

    len(token_lines(source) - docstring_lines(tree) - blank), where blank
    is the rows whose text is whitespace: a blank line inside a SQL body
    is still a blank line.
    """
    raise NotImplementedError('ARCHITECTURE §13 step 15: code_lines')


def test_member_budgets():
    """§3: the set of .py files under dibs/ (posix paths from ROOT) equals
    MEMBER_BUDGETS' keys, and the dict of modules whose members_of exceeds
    its budget is empty - `assert not over` (WPS520)."""
    raise NotImplementedError('needs tests/test_architecture (§13 step 15)')


def test_layering():
    """§4: over every file's import_edges, the list of (importer, imported)
    with LEVELS[importer] <= LEVELS[imported] is empty - unpack the pair,
    never subscript it. __main__ is L6, so the entry's cli edge is
    downward; the dotted `import dibs.x` form is WPS301-banned, so
    ImportFrom is the complete edge set."""
    raise NotImplementedError('needs tests/test_architecture (§13 step 15)')


def test_size_budget():
    """SSoT §2: sum(code_lines) over sorted dibs/**/*.py <= HARD_STOP, the
    total in the assertion message so `make test` prints it on failure
    (1654 expected at ca34e33 - if the test says otherwise, its counter is
    §2's reference: correct the §2 sentence, never the stop); the file
    count <= FILE_CAP."""
    raise NotImplementedError('needs tests/test_architecture (§13 step 15)')
