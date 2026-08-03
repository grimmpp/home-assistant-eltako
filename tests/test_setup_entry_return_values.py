"""Static check that the Home Assistant setup callbacks always return a bool.

Reported in https://github.com/grimmpp/home-assistant-eltako/pull/142 ("work without
errors in HAOS 2024.12.1"): several error paths of `async_setup_entry` used a bare
`return`. Home Assistant checks the return value of these callbacks and logs

    <domain>.async_setup_entry did not return boolean

so a bare `return` turns a handled configuration problem into an error in the log.
`None` is falsy, so the entry is treated as failed either way - the difference is only
whether the user sees the readable warning of the integration or a generic error.

The check is static on purpose: these branches are only reached with a broken
configuration and are therefore not covered by the other tests.
"""
import ast
import os
import unittest
from unittest import TestCase

COMPONENT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'custom_components', 'eltako')

# callbacks whose return value Home Assistant evaluates
BOOL_CALLBACKS = {
    'async_setup',
    'async_setup_entry',
    'async_unload_entry',
    'async_remove_config_entry_device',
    'async_migrate_entry',
}


def _python_files() -> list[str]:
    files = []
    for root, _dirs, names in os.walk(COMPONENT_DIR):
        if 'frontend' in root:
            continue
        files.extend(os.path.join(root, n) for n in names if n.endswith('.py'))
    return sorted(files)


def _returns_without_value(func: ast.AST) -> list[int]:
    """Line numbers of `return` statements without a value, ignoring nested functions.

    ast.walk() cannot be used here: it does not prune, so the returns of a nested
    callback would be attributed to the outer function.
    """
    lines = []

    def visit(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue    # own scope, checked separately if it is a callback itself
            if isinstance(child, ast.Return) and child.value is None:
                lines.append(child.lineno)
            visit(child)

    visit(func)
    return sorted(lines)


class TestSetupCallbackReturnValues(TestCase):

    def test_bool_callbacks_never_return_none(self):
        offenders = []

        for path in _python_files():
            with open(path, encoding='utf-8') as f:
                tree = ast.parse(f.read(), filename=path)

            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if node.name not in BOOL_CALLBACKS:
                    continue
                # only the module level callbacks are called by Home Assistant
                for lineno in _returns_without_value(node):
                    offenders.append(f"{os.path.basename(path)}:{lineno} in {node.name}()")

        self.assertEqual(offenders, [],
                         "bare 'return' in a callback which Home Assistant expects to return a "
                         "bool. Use 'return False' instead:\n  " + "\n  ".join(offenders))

    def test_the_check_finds_a_bare_return(self):
        """Guard against the check silently passing because it walks the tree wrongly."""
        tree = ast.parse("async def async_setup_entry(hass, entry) -> bool:\n"
                         "    if True:\n"
                         "        return\n"
                         "    return True\n")
        func = tree.body[0]

        self.assertEqual(_returns_without_value(func), [3])

    def test_nested_functions_are_not_reported(self):
        tree = ast.parse("async def async_setup_entry(hass, entry) -> bool:\n"
                         "    def callback(event):\n"
                         "        return\n"
                         "    return True\n")
        func = tree.body[0]

        self.assertEqual(_returns_without_value(func), [])


if __name__ == '__main__':
    unittest.main()
