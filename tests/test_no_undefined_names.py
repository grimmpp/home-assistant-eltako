"""Static check for undefined names in the integration.

Some code paths (e.g. callbacks which Home Assistant only calls on user interaction) are not
covered by the other tests. A missing import there only shows up at runtime - this test finds
those cases by resolving every name used in a module against its imports, definitions and
builtins. It deliberately understands `from .const import *` style star imports, which this
integration uses a lot.
"""
import ast
import builtins
import os
import unittest
from unittest import TestCase

COMPONENT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'custom_components', 'eltako')

# modules which are imported with `import *` somewhere in the integration
STAR_IMPORT_MODULES = {
    '.const': 'custom_components.eltako.const',
    '.device': 'custom_components.eltako.device',
    '.gateway': 'custom_components.eltako.gateway',
    '.config_helpers': 'custom_components.eltako.config_helpers',
    'eltakobus.eep': 'eltakobus.eep',
    'eltakobus.message': 'eltakobus.message',
    'eltakobus.util': 'eltakobus.util',
    'homeassistant.const': 'homeassistant.const',
}


def _names_of_module(module_name: str) -> set[str]:
    import importlib
    try:
        module = importlib.import_module(module_name)
    except Exception:   # noqa: BLE001 - module cannot be imported in the test environment
        return set()
    return {name for name in dir(module) if not name.startswith('_')}


class NameCollector(ast.NodeVisitor):
    """Collects defined and used names of a module (module level and function scopes merged)."""

    def __init__(self):
        self.defined: set[str] = set()
        self.used: set[tuple[str, int]] = set()
        self.star_imports: list[str] = []

    def visit_Import(self, node):
        for alias in node.names:
            self.defined.add((alias.asname or alias.name).split('.')[0])

    def visit_ImportFrom(self, node):
        module = ('.' * (node.level or 0)) + (node.module or '')
        for alias in node.names:
            if alias.name == '*':
                self.star_imports.append(module)
            else:
                self.defined.add(alias.asname or alias.name)

    def visit_FunctionDef(self, node):
        self.defined.add(node.name)
        self._add_arguments(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        self.defined.add(node.name)
        self._add_arguments(node)
        self.generic_visit(node)

    def _add_arguments(self, node):
        args = node.args
        for arg in list(args.args) + list(args.posonlyargs) + list(args.kwonlyargs):
            self.defined.add(arg.arg)
        if args.vararg:
            self.defined.add(args.vararg.arg)
        if args.kwarg:
            self.defined.add(args.kwarg.arg)

    def visit_ClassDef(self, node):
        self.defined.add(node.name)
        self.generic_visit(node)

    def visit_Lambda(self, node):
        self._add_arguments(node)
        self.generic_visit(node)

    def visit_ExceptHandler(self, node):
        if node.name:
            self.defined.add(node.name)
        self.generic_visit(node)

    def visit_comprehension(self, node):
        self.generic_visit(node)

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load):
            self.used.add((node.id, node.lineno))
        else:
            self.defined.add(node.id)
        self.generic_visit(node)

    def visit_Global(self, node):
        self.defined.update(node.names)

    def visit_arg(self, node):
        self.defined.add(node.arg)


class TestNoUndefinedNames(TestCase):

    def test_all_used_names_are_defined_or_imported(self):
        builtin_names = set(dir(builtins)) | {'__file__', '__name__', '__doc__', '__package__', 'self', 'cls'}
        star_cache = {}
        problems = []

        for file in sorted(os.listdir(COMPONENT_DIR)):
            if not file.endswith('.py'):
                continue
            path = os.path.join(COMPONENT_DIR, file)
            with open(path, encoding='utf-8') as handle:
                tree = ast.parse(handle.read(), filename=path)

            collector = NameCollector()
            collector.visit(tree)

            available = set(collector.defined) | builtin_names
            for module in collector.star_imports:
                target = STAR_IMPORT_MODULES.get(module, module.lstrip('.'))
                if target not in star_cache:
                    star_cache[target] = _names_of_module(target)
                available |= star_cache[target]

            for name, line in sorted(collector.used, key=lambda item: item[1]):
                if name not in available:
                    problems.append(f"{file}:{line} uses undefined name '{name}'")

        self.assertEqual(problems, [], msg="Undefined names found:\n  " + "\n  ".join(problems))


if __name__ == '__main__':
    unittest.main()
