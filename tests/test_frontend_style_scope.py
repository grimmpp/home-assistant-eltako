"""The styles of one page must not reach into the markup of another one.

The panel puts the styles of *every* page into one ``<style>`` of its shadow root
(eltako-panel.js, ``_renderShell``). There is no scoping - a rule written on the radio page
applies on the HA entities page as well. That is how the table of the HA entities page broke:
radio.js styled ``.controls { display: flex; flex-direction: column }`` and
``.control-row { display: flex }`` for its own filter boxes, and control.js uses exactly those
two names on a ``<tr>`` and a ``<td>``. The rows stopped being table rows, so the cells left
the columns of their own table head and the On/Off buttons stood underneath each other, while
the head still spanned the full width - and nothing about either page said why.

The rule this pins: every selector a page brings *of its own* has to be anchored to at least
one class which no other page and no shared renderer uses. ``.type-chip.on`` is fine
(``.type-chip`` belongs to one page, even though ``on`` is used everywhere), a plain
``.controls`` is not. What comes out of the shared style constants (FORM_STYLES,
DETAILS_STYLES, ...) is meant for every page and is left out - the page css is read through
node, so the constants are resolved exactly as the panel resolves them.
"""
import json
import os
import re
import shutil
import subprocess
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND = os.path.join(REPO, 'custom_components', 'eltako', 'frontend')
PAGES_DIR = os.path.join(FRONTEND, 'pages')
LIB_DIR = os.path.join(FRONTEND, 'lib')
NODE = shutil.which('node')

# The css of every page with the shared style constants of lib/ removed - what is left is what
# this page alone adds to the stylesheet of the panel.
SCRIPT = """
import { readdirSync, writeFileSync } from 'node:fs';
globalThis.window = { eltakoStandalone: true };
const [, , libDir, pagesDir, out] = process.argv;
const shared = [];
for (const file of readdirSync(libDir)) {
  const module = await import(libDir + '/' + file);
  for (const [name, value] of Object.entries(module))
    if (name.endsWith('STYLES') && typeof value === 'string') shared.push(value);
}
const css = {};
for (const file of readdirSync(pagesDir).filter((name) => name.endsWith('.js'))) {
  const { page } = await import(pagesDir + '/' + file);
  let own = page.styles || '';
  for (const block of shared) own = own.split(block).join('');
  css[file] = own;
}
writeFileSync(out, JSON.stringify(css));
"""

# Rules which really are meant for markup of other pages. Every entry is a class which a
# *shared* renderer or the global stylesheet brings along, so the rule has nowhere else to
# live - and every new entry needs that same kind of reason, not just a failing test.
ALLOWED = {
    # .chip is a global class (lib/styles.js); devices_config.js puts chips in a table as well
    ('help.js', 'td .chip'),
    # the state chips of a device are also rendered by lib/details.js (the modal card)
    ('home.js', '.state-chip'),
    ('home.js', '.state-chip b'),
    ('home.js', '.state-chip[hidden]'),
    ('home.js', '.device-states[hidden]'),
    ('home.js', 'button.state-chip[disabled]'),
    # .tag.<state> is the family of lib/styles.js (.tag.taught, .tag.unknown, ...)
    ('tests.js', '.tag.ok'),
}


def page_css() -> dict:
    """{page file: the css this page alone contributes}, resolved through node."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        script = os.path.join(tmp, 'css.mjs')
        out = os.path.join(tmp, 'css.json')
        with open(script, 'w', encoding='utf-8') as handle:
            handle.write(SCRIPT)
        process = subprocess.run([NODE, script, LIB_DIR, PAGES_DIR, out],
                                 capture_output=True, text=True, timeout=120, cwd=REPO)
        assert process.returncode == 0, f"node failed:\n{process.stderr[-2000:]}"
        with open(out, encoding='utf-8') as handle:
            return json.load(handle)


def classes_used(markup: str) -> set:
    """The class names of ``class="..."`` - the interpolated parts are skipped."""
    names = set()
    for value in re.findall(r'class="([^"]*)"', markup):
        for token in re.split(r'\s+|\$\{[^}]*\}', value):
            if token and re.fullmatch(r"[a-zA-Z][\w-]*", token):
                names.add(token)
    return names


def selectors(css: str) -> list:
    """Every single selector of a stylesheet - comments, at-rules and keyframe steps out."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    # @keyframes brings blocks of its own ("0% { ... }") which are no selectors
    css = re.sub(r"@keyframes[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", "", css)
    found = []
    for block in re.findall(r"([^{}]+)\{", css):
        block = block.strip()
        if not block or block.startswith('@'):
            continue
        found.extend(part.strip() for part in block.split(',') if part.strip())
    return found


def _classes_of(directory: str, files=None) -> dict:
    names = {}
    for file in sorted(files if files is not None else os.listdir(directory)):
        if not file.endswith('.js'):
            continue
        with open(os.path.join(directory, file), encoding='utf-8') as handle:
            names[file] = classes_used(handle.read())
    return names


def leaking_selectors(css: dict, markup: dict, shared_markup: set) -> list:
    """(page, selector) of every rule of a page which can match markup of another one."""
    problems = []
    for page, own in css.items():
        foreign = set(shared_markup).union(
            *[names for name, names in markup.items() if name != page]) \
            if len(markup) > 1 else set(shared_markup)
        for selector in selectors(own):
            if (page, selector) in ALLOWED:
                continue
            names = set(re.findall(r"\.([a-zA-Z][\w-]*)", selector))
            if not names or names <= foreign:
                problems.append((page, selector))
    return problems


@unittest.skipUnless(NODE, 'node is not installed - the page styles cannot be resolved here')
class TestPageStylesStayOnTheirPage(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.css = page_css()
        cls.markup = _classes_of(PAGES_DIR)
        cls.shared = set().union(*_classes_of(LIB_DIR).values())

    def test_no_page_style_reaches_into_another_page(self):
        problems = leaking_selectors(self.css, self.markup, self.shared)

        self.assertEqual([], problems,
                         msg="these rules apply on the other pages of the panel as well - give "
                             "them a name of their own (.radio-controls instead of .controls), "
                             "or move them to lib/ if they really are shared")

    def test_the_pages_really_were_read(self):
        """A broken parse would let everything pass, so the input itself is checked."""
        self.assertGreater(len(self.css), 8)
        with_styles = [name for name, css in self.css.items() if selectors(css)]
        self.assertGreater(len(with_styles), 5, msg=f"only {with_styles} had styles of their own")
        self.assertIn('type-chip', self.markup['control.js'])

    def test_the_check_catches_the_bug_it_was_written_for(self):
        """radio.js styling a plain .controls while control.js puts it on a <td>."""
        css = {'radio.js': '.controls { display: flex; } .radio-legend { gap: 4px; }',
               'control.js': '.control-row td { vertical-align: middle; }'}
        markup = {'radio.js': {'controls', 'radio-legend'},
                  'control.js': {'controls', 'control-row'}}

        problems = leaking_selectors(css, markup, set())

        self.assertIn(('radio.js', '.controls'), problems)
        self.assertNotIn(('radio.js', '.radio-legend'), problems)


if __name__ == '__main__':
    unittest.main()
