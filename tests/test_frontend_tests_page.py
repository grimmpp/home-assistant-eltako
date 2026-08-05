"""The 'Tests' page of the web ui and its contract with device_tests.py.

The frontend is plain javascript without a build step, so nothing tells you that a renamed
element id or a renamed parameter stopped working - the button just does nothing at runtime.
These are static checks on the shipped files:

* every `getElementById("x")` of a page has a matching `id="x"` in the same page (all pages,
  not only this one - the mistake is the same everywhere)
* the websocket commands and the parameter names the page sends are the ones the backend reads
* the page uses the shared look of the other pages instead of its own layout
"""
import os
import re
from unittest import TestCase

from custom_components.eltako import device_tests

FRONTEND = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                        'custom_components', 'eltako', 'frontend')
PAGES_DIR = os.path.join(FRONTEND, 'pages')

# every test of the backend has its own start button on the page - the id is its test id
TEST_ID_OF_START_BUTTON = [descriptor['id'] for descriptor in device_tests.TEST_DESCRIPTORS]


def read(*parts) -> str:
    with open(os.path.join(FRONTEND, *parts), encoding='utf-8') as handle:
        return handle.read()


def page_files() -> list[str]:
    return sorted(name for name in os.listdir(PAGES_DIR) if name.endswith('.js'))


class TestElementIdsAreWired(TestCase):
    """A handler which looks up an id that is never rendered is dead code - silently."""

    def test_every_looked_up_id_is_rendered(self):
        for name in page_files():
            source = read('pages', name)
            rendered = set(re.findall(r'id="([a-zA-Z0-9_-]+)"', source))
            looked_up = set(re.findall(r'getElementById\("([a-zA-Z0-9_-]+)"\)', source))

            self.assertEqual(set(), looked_up - rendered,
                             msg=f'{name} looks up ids which it never renders')

    def test_the_tests_page_wires_all_of_its_controls(self):
        """The other direction for this page: a rendered control without a handler does nothing.

        'Referenced' is any place which names the id - besides getElementById() that is
        `addressList("cover-addresses")`, which looks the element up through a parameter.
        """
        source = read('pages', 'tests.js')
        rendered = set(re.findall(r'id="([a-zA-Z0-9_-]+)"', source))
        # the id="..." attributes themselves must not count as a reference
        without_markup = re.sub(r'id="[a-zA-Z0-9_-]+"', '', source)
        referenced = {name for name in rendered if f'"{name}"' in without_markup}

        self.assertEqual(set(), rendered - referenced,
                         msg='controls of the tests page which no code refers to')


class TestTheContractWithTheBackend(TestCase):

    def setUp(self):
        self.source = read('pages', 'tests.js')

    def test_websocket_command_names(self):
        for constant in (device_tests.WS_DEVICE_TESTS_INFO, device_tests.WS_DEVICE_TESTS_START,
                         device_tests.WS_DEVICE_TESTS_STOP, device_tests.WS_DEVICE_TESTS_SUBSCRIBE):
            self.assertIn(f'"{constant}"', self.source, msg=constant)

    def test_the_page_offers_every_test_of_the_backend(self):
        for descriptor in device_tests.TEST_DESCRIPTORS:
            self.assertIn(f'"{descriptor["id"]}"', self.source, msg=descriptor['id'])

    def test_every_test_can_be_started_from_the_page(self):
        started = set(re.findall(r'start\("(\w+)"', self.source))

        self.assertEqual(set(device_tests.TEST_RUNNERS), started, msg=started)

    def test_the_parameters_the_page_sends_are_the_ones_the_backend_reads(self):
        """One renamed key and the test runs with a default instead of the entered value -
        without any error message. Checked for every test the page can start."""
        import inspect

        for test_id, runner in device_tests.TEST_RUNNERS.items():
            backend = inspect.getsource(runner)
            match = re.search(rf'start\("{test_id}",\s*\{{(.*?)\}}\);?\s*\n', self.source, re.S)
            self.assertIsNotNone(match, msg=f"the page does not start '{test_id}'")

            for name in re.findall(r'^\s*(\w+):', match.group(1), re.M):
                self.assertIn(f'"{name}"', backend,
                              msg=f"the runner of '{test_id}' does not read '{name}'")

    def test_the_result_fields_the_page_shows_are_produced_by_the_backend(self):
        import inspect

        burst = inspect.getsource(device_tests.run_burst_test)
        cover = inspect.getsource(device_tests.run_cover_test)

        for field in ('sent', 'received', 'missing', 'missing_addresses', 'other_messages'):
            self.assertIn(f"'{field}'", burst.replace('"', "'"), msg=f'burst result: {field}')
        for field in ('reaction_s', 'measured_s', 'reported_s', 'end_position', 'problems',
                      'recommendations', 'interference_count', 'up_s', 'down_s',
                      'configured_opens', 'configured_closes'):
            self.assertIn(f"'{field}'", cover.replace('"', "'"), msg=f'cover result: {field}')


class TestTheSharedLook(TestCase):
    """The page used its own form markup and hardcoded colours; it uses the shared look now."""

    def setUp(self):
        self.source = read('pages', 'tests.js')
        self.styles = read('lib', 'styles.js')

    def test_it_uses_the_shared_form_and_table_styles(self):
        self.assertIn('FORM_STYLES', self.source)
        for marker in ('class="form-card"', 'class="form-grid"', 'class="field"',
                       'class="table-wrapper"', 'class="cards"'):
            self.assertIn(marker, self.source, msg=marker)

    def test_status_and_results_are_summarized_in_cards(self):
        self.assertIn('card("Gateways"', self.source)
        self.assertIn('card("Test state"', self.source)
        self.assertIn('card("Last result"', self.source)
        self.assertIn('card("Runs"', self.source)          # burst summary
        self.assertIn('card("Movements"', self.source)     # cover summary

    def test_a_running_test_is_visible_and_blocks_the_start_buttons(self):
        self.assertIn('dt-running', self.source)
        self.assertIn('@keyframes eltako-dt-pulse', self.source)
        # every start button is disabled while a test runs - one test at a time
        starts = re.findall(r'id="(\w+)-start"', self.source)
        disabled = re.findall(r'info\.running[^\n]*"disabled"', self.source)

        self.assertEqual(sorted(starts), sorted(TEST_ID_OF_START_BUTTON), msg=starts)
        self.assertEqual(len(starts), len(disabled), msg="a start button without a disabled state")
        # ... and a disabled button has to look disabled
        self.assertIn('button.action:disabled', self.styles)

    def test_log_colours_follow_the_theme(self):
        """A hardcoded green/red is unreadable on a dark theme."""
        log_rules = re.findall(r'\.dt-log \.\w+ \{[^}]*\}', self.source)

        self.assertTrue(log_rules)
        for rule in log_rules:
            self.assertIn('var(--', rule, msg=rule)
