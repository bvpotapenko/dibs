"""Architecture guard: the budgets are a test, not a hope (§13 step 15).

SSoT §2 (size), ARCHITECTURE §3 (member budgets) and §4 (layering) are
held here as one table each. A number changes only together with the
document it mirrors: a red case here is a design drift, never a test
to edit alone. AST + tokenize over dibs/, no imports of the package.
"""

from types import MappingProxyType

HARD_STOP = 1700  # SSoT §2: code lines, counted as §2 defines them
FILE_CAP = 18  # SSoT §2: .py files under dibs/
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
# ARCHITECTURE §4: module -> level; a module imports strictly lower ones
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
    '__main__': 5,
})


def test_member_budgets():
    """§3: for every module in MEMBER_BUDGETS, count top-level FunctionDef
    and ClassDef nodes (ast.parse; constants do not count) and assert
    count <= budget; also assert the set of modules on disk equals the
    table's keys, so a new file is a documented decision."""
    raise NotImplementedError('needs tests/test_architecture (§13 step 15)')


def test_layering():
    """§4: for every `from dibs… import` / `import dibs…` edge outside an
    `if TYPE_CHECKING:` block, LEVELS[importer] > LEVELS[imported];
    `dibs.verbs.*` counts as `verbs`, `dibs.records`/`dibs.runtime` as
    themselves. Assert the list of violating edges is empty."""
    raise NotImplementedError('needs tests/test_architecture (§13 step 15)')


def test_size_budget():
    """SSoT §2: code lines over dibs/ - non-blank, not comment-only, not
    inside a docstring (the first statement of a module/class/function
    when it is a string); body lines of multi-line SQL/template strings
    count - total <= HARD_STOP, and .py files under dibs/ <= FILE_CAP.
    Report the number in the assertion message so `make test` prints
    it on failure."""
    raise NotImplementedError('needs tests/test_architecture (§13 step 15)')
