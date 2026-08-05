"""The two views of the web ui (simple / expert) have to stay wired up correctly.

The panel shows a page only if the page belongs to the current view (`page.modes`, see
frontend/eltako-panel.js). A typo in that list - or a home page which is not reachable in its
own view - would empty the navigation, and the frontend has no build step which would notice.
So the page modules and the shell are read here and checked against each other:

* every `modes` value is one of the views the shell defines
* each view has its home page, and that page really belongs to it
* the simple view contains the device page and none of the expert-only pages
* Home Assistant starts in the simple view, the standalone runtime in the expert one
"""
import os
import re
import unittest

FRONTEND = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                        'custom_components', 'eltako', 'frontend')
PANEL_JS = os.path.join(FRONTEND, 'eltako-panel.js')
PAGES_DIR = os.path.join(FRONTEND, 'pages')

# the default of the shell: a page without `modes` belongs to the expert view only
DEFAULT_MODES = ('expert',)


def _read(path: str) -> str:
    with open(path, encoding='utf-8') as handle:
        return handle.read()


def _page_modes() -> dict[str, tuple[str, ...]]:
    """{page id: views it appears in} of every module in frontend/pages."""
    result = {}
    for name in sorted(os.listdir(PAGES_DIR)):
        if not name.endswith('.js'):
            continue
        source = _read(os.path.join(PAGES_DIR, name))
        page_id = re.search(r'^\s*id:\s*"([^"]+)"', source, re.MULTILINE)
        modes = re.search(r'^\s*modes:\s*\[([^\]]*)\]', source, re.MULTILINE)
        assert page_id, f'{name} does not declare an id'
        result[page_id.group(1)] = (tuple(re.findall(r'"([^"]+)"', modes.group(1)))
                                    if modes else DEFAULT_MODES)
    return result


def _shell_modes() -> dict[str, str]:
    """{view: id of its home page} of the MODES object of the shell."""
    source = _read(PANEL_JS)
    # import { page as overviewPage } from "./pages/overview.js" -> the id of that module
    id_of_import = {}
    for constant, module in re.findall(r'import \{ page as (\w+) \} from "\./pages/([^"]+)"', source):
        page_id = re.search(r'^\s*id:\s*"([^"]+)"', _read(os.path.join(PAGES_DIR, module)), re.MULTILINE)
        id_of_import[constant] = page_id.group(1)

    body = source.split('const MODES = {', 1)[1].split('\n};', 1)[0]
    return {mode: id_of_import[constant] for mode, constant
            in re.findall(r'(\w+):\s*\{[^}]*home:\s*(\w+)\.id', body, re.DOTALL)}


class TestViewModes(unittest.TestCase):

    def setUp(self):
        self.pages = _page_modes()
        self.shell = _shell_modes()
        self.panel = _read(PANEL_JS)

    def test_the_shell_defines_the_two_views(self):
        self.assertEqual({'user', 'expert'}, set(self.shell))

    def test_every_page_uses_a_known_view(self):
        for page_id, modes in self.pages.items():
            self.assertTrue(modes, msg=f"page '{page_id}' has an empty modes list")
            for mode in modes:
                self.assertIn(mode, self.shell, msg=f"page '{page_id}' uses an unknown view")

    def test_every_view_has_a_home_page_which_belongs_to_it(self):
        # the home of a view is what the panel opens when no page is bookmarked, so it has to
        # be a page of that very view - otherwise the panel would start on an invisible page
        for mode, page_id in self.shell.items():
            self.assertIn(page_id, self.pages, msg=f"the home page of '{mode}' does not exist")
            self.assertIn(mode, self.pages[page_id],
                          msg=f"the home page of '{mode}' does not belong to that view")

    def test_the_simple_view_shows_the_devices_and_hides_the_expert_pages(self):
        simple = {page_id for page_id, modes in self.pages.items() if 'user' in modes}

        self.assertIn('home', simple)
        for page_id in ('overview', 'devices', 'telegrams', 'statistics', 'tests', 'settings'):
            self.assertNotIn(page_id, simple,
                             msg=f"'{page_id}' needs expert knowledge and must not be in the simple view")

    def test_home_assistant_starts_simple_and_the_standalone_runtime_expert(self):
        self.assertIn('const DEFAULT_MODE = window.eltakoStandalone ? "expert" : "user";', self.panel)

    def test_the_view_is_remembered_across_reloads(self):
        self.assertIn('MODE_STORAGE_KEY', self.panel)
        self.assertIn('window.localStorage.setItem(MODE_STORAGE_KEY, mode)', self.panel)
        self.assertIn('window.localStorage.getItem(MODE_STORAGE_KEY)', self.panel)
