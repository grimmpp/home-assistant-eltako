"""The web ui says what runs, and it says why a button cannot be pressed.

Companion of test_activity.py, which pins the backend answer: this one pins what the panel
makes of it (frontend/lib/activity.js). Three things have to hold, because together they are
what turns "the button does nothing" into "something is running, it takes minutes, wait":

* the banner names every job in plain words, how far it is and since when
* it states the consequence - the bus is deaf, other operations are refused - so waiting is
  understood as the right thing to do and not as a hang
* every button marked `data-busy-block` is disabled *and carries the reason*, and gets its
  own title back when the job is done (it must not stay locked or lose its own tooltip)

Node is only used as a javascript engine; the test is skipped when node is not installed. The
elements are a small stub - the module only uses querySelectorAll, the attributes and
`disabled`.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND = os.path.join(REPO, 'custom_components', 'eltako', 'frontend')
NODE = shutil.which('node')

SCRIPT = r"""
const activity = await import(`${process.argv[2]}/lib/activity.js`);

/* --------------------------------------------------------------- element stub */

class El {
  constructor(attributes = {}) {
    this.attributes = { ...attributes };
    this.disabled = false;
  }
  getAttribute(name) { return name in this.attributes ? this.attributes[name] : null; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  hasAttribute(name) { return name in this.attributes; }
  removeAttribute(name) { delete this.attributes[name]; }
  get title() { return this.attributes.title; }
  set title(value) { this.attributes.title = value; }
}

const anyButton = new El({ 'data-busy-block': 'any' });
const busButton = new El({ 'data-busy-block': 'bus', title: 'scan the bus of this gateway' });
const detectButton = new El({ 'data-busy-block': 'detection' });
const otherGateway = new El({ 'data-busy-block': 'gateway:9' });
const plainButton = new El({});                       // not marked: never touched
const all = [anyButton, busButton, detectButton, otherGateway];
const root = { querySelectorAll: () => all };

const at = (seconds) => new Date(Date.now() - seconds * 1000).toISOString();
const scan = {
  kind: 'bus', gateway_id: 1, gateway_name: 'FAM14', reason: 'bus scan',
  blocks: ['bus', 'gateway:1'], started_at: at(150),
  progress: { gateway_id: 1, positions_total: 14, positions_done: 3, percent: 24 },
};
const detection = {
  kind: 'detection', step: 'Probing the free serial ports', stage: 'ports',
  blocks: ['detection', 'bus'], started_at: at(180),
};

const state = () => all.map((element) => ({
  token: element.getAttribute('data-busy-block'),
  disabled: element.disabled,
  title: element.getAttribute('title'),
  locked: element.hasAttribute('data-busy-locked'),
}));

activity.applyBusyLocks(root, [scan]);
const whileScanning = state();

activity.applyBusyLocks(root, []);                    // the scan is done
const afterwards = state();

console.log(JSON.stringify({
  idle: activity.renderActivity({ busy: false, jobs: [] }),
  scanning: activity.renderActivity({ busy: true, jobs: [scan] }),
  both: activity.renderActivity({ busy: true, jobs: [detection, scan] }),
  detectionOnly: activity.renderActivity({ busy: true, jobs: [{ ...detection, blocks: ['detection'] }] }),
  described: [detection, scan,
              { kind: 'bus', gateway_id: 2, gateway_name: 'FGW14', reason: 'teaching in the senders' },
              { kind: 'bus', gateway_id: 3, reason: 'base id / version request' }]
             .map((job) => activity.describeJob(job)),
  blocking: {
    bus: !!activity.blockingJob([scan], 'bus'),
    detection: !!activity.blockingJob([scan], 'detection'),
    any: !!activity.blockingJob([scan], 'any'),
    ownGateway: !!activity.blockingJob([scan], 'gateway:1'),
    otherGateway: !!activity.blockingJob([scan], 'gateway:9'),
  },
  whileScanning, afterwards,
  plainUntouched: plainButton.disabled === false && plainButton.getAttribute('title') === null,
}, null, 1));
"""


@unittest.skipUnless(NODE, 'node is not installed')
class TestTheActivityBanner(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'activity.mjs')
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write(SCRIPT)
            result = subprocess.run([NODE, path, FRONTEND], capture_output=True, text=True,
                                    timeout=120)
        if result.returncode != 0:
            raise AssertionError(f'node failed:\n{result.stderr}')
        cls.result = json.loads(result.stdout)

    def test_nothing_running_shows_nothing(self):
        self.assertEqual('', self.result['idle'])

    def test_the_banner_names_the_job_its_progress_and_since_when(self):
        banner = self.result['scanning']
        self.assertIn('please wait', banner)
        self.assertIn('Reading the bus of FAM14', banner)
        self.assertIn('position 4/14', banner)          # the position being read, see bus_scan.js
        self.assertIn('24%', banner)
        self.assertIn('since 2 min', banner)

    def test_the_banner_says_why_waiting_is_the_right_thing(self):
        banner = self.result['scanning']
        self.assertIn('a few minutes', banner)
        self.assertIn('do not react', banner)
        self.assertIn('disabled until it is done', banner)
        self.assertIn('page updates itself', banner)

    def test_a_job_which_does_not_touch_the_bus_gets_the_short_hint(self):
        banner = self.result['detectionOnly']
        self.assertIn('a few minutes', banner)
        self.assertNotIn('do not react', banner)

    def test_several_jobs_are_listed_together(self):
        banner = self.result['both']
        self.assertIn('2 things are running', banner)
        self.assertIn('Searching for gateways and devices', banner)
        self.assertIn('Reading the bus of FAM14', banner)

    def test_every_kind_of_job_has_words_of_its_own(self):
        titles = [entry['title'] for entry in self.result['described']]
        self.assertEqual(['Searching for gateways and devices', 'Reading the bus of FAM14',
                          'Teaching in the senders on FGW14', 'Asking Gateway 3 for its base id'],
                         titles)

    def test_a_job_blocks_exactly_what_it_says(self):
        self.assertEqual({'bus': True, 'detection': False, 'any': True,
                          'ownGateway': True, 'otherGateway': False},
                         self.result['blocking'])

    def test_a_blocked_button_is_disabled_and_says_why(self):
        by_token = {entry['token']: entry for entry in self.result['whileScanning']}
        self.assertTrue(by_token['any']['disabled'])
        self.assertTrue(by_token['bus']['disabled'])
        self.assertRegex(by_token['bus']['title'], r'Not possible right now.*Please wait')
        # a scan of this bus does not stop a detection button or another gateway
        self.assertFalse(by_token['detection']['disabled'])
        self.assertFalse(by_token['gateway:9']['disabled'])

    def test_the_buttons_come_back_with_their_own_tooltip(self):
        by_token = {entry['token']: entry for entry in self.result['afterwards']}
        self.assertFalse(by_token['bus']['disabled'])
        self.assertFalse(by_token['bus']['locked'])
        self.assertEqual('scan the bus of this gateway', by_token['bus']['title'])
        # a button without a tooltip of its own must not keep the "please wait" one
        self.assertIsNone(by_token['any']['title'])

    def test_a_button_which_is_not_marked_is_never_touched(self):
        self.assertTrue(self.result['plainUntouched'])


class TestThePanelShowsItEverywhere(unittest.TestCase):
    """The banner is worth nothing if it only appears on the page which started the job."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(FRONTEND, 'eltako-panel.js'), encoding='utf-8') as handle:
            cls.panel = handle.read()

    def test_the_shell_has_a_place_for_it_above_the_toolbar(self):
        self.assertIn('id="activity"', self.panel)
        self.assertLess(self.panel.index('id="activity"'), self.panel.index('id="toolbar"'))

    def test_it_is_rendered_on_every_page_not_by_a_page(self):
        render = re.search(r'_render\(\) \{(.*?)\n  \}', self.panel, re.DOTALL)
        self.assertIsNotNone(render, 'eltako-panel.js has no _render()')
        self.assertIn('this._renderActivity()', render.group(1))

    def test_it_is_polled_while_the_panel_is_open(self):
        self.assertIn('_pollActivity()', self.panel)
        self.assertIn('WS.ACTIVITY', self.panel)

    def test_the_locks_are_applied_after_every_render(self):
        self.assertIn('this._applyBusyLocks()', self.panel)

    def test_pages_which_start_something_long_refresh_it_at_once(self):
        for name in ('home.js', 'overview.js', 'devices_config.js'):
            with open(os.path.join(FRONTEND, 'pages', name), encoding='utf-8') as handle:
                self.assertIn('refreshActivity', handle.read(),
                              f'{name} starts a long job without telling the panel')


if __name__ == '__main__':
    unittest.main()
