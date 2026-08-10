""""Remove all & search again" really searches.

The button deletes every device created in the web ui and then starts a detection. It used to
ask a *second* time - with the wording of the plain "Search devices" button, a question nobody
expects right after having confirmed "and search again". Answering that one with "cancel" (or
a browser which suppresses a dialog opened straight after another) left the devices deleted
and nothing searched: exactly the "remove all & search again does not search, pressing search
afterwards does" of the bug report.

Two more things this pins:

* deleting the devices rewrites the options of every gateway, which makes Home Assistant
  reload it - for a few seconds it is disconnected and its bus cannot be read. The search
  waits for the gateways instead of probing while they come up.
* a run which the backend refuses (`started: false`) is said out loud instead of leaving a
  progress bar which never moves.

Node is only used as a javascript engine; the test is skipped when node is not installed.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND = os.path.join(REPO, 'custom_components', 'eltako', 'frontend')
NODE = shutil.which('node')

SCRIPT = r"""
const { page } = await import(`${process.argv[2]}/pages/home.js`);

globalThis.requestAnimationFrame = (callback) => setTimeout(callback, 0);

/**
 * One run of the page. `options.run` is the answer of eltako/plug_and_play/run,
 * `options.reloadPolls` for how many polls the gateway is away after the removal - which is
 * what home assistant does with a gateway whose options were rewritten.
 */
function makeContext(log, options = {}) {
  let reloading = 0;
  const gateways = () => (reloading > 0 ? [] : [{ id: 1, name: 'FAM14', connected: true }]);
  const ctx = {
    state: {
      configuredDevices: [
        { platform: 'light', address: '00-00-00-01', gateway_id: 1, editable: true },
        { platform: 'sensor', address: 'FF-EE-DD-CC', gateway_id: 1, editable: false },
      ],
      plugAndPlay: { running: false },
      deviceForm: { platforms: [], gateways: [] },
      integrationInfo: { gateways: gateways() },
      statistics: {},
    },
    api: {
      lastError: null,
      async call(type, payload) {
        log.push({ ws: type, payload: payload || {} });
        if (type === 'eltako/devices/remove_all') {
          reloading = options.reloadPolls || 0;
          return { removed: 1, devices: [] };
        }
        if (type === 'eltako/devices/list') return { devices: [] };
        if (type === 'eltako/plug_and_play/status') return { running: false };
        if (type === 'eltako/plug_and_play/run') {
          return options.run || { started: true, status: { running: false } };
        }
        return {};
      },
    },
    async loadIntegrationInfo() {
      if (reloading > 0) reloading -= 1;
      ctx.state.integrationInfo = { gateways: gateways() };
      log.push({ ws: 'eltako/integration_info', gateways: gateways().length });
    },
    loadStatistics: async () => { log.push({ ws: 'eltako/telegram_log/statistics' }); },
    requestContentRender: () => log.push({ render: 'content' }),
    requestRender: () => log.push({ render: 'full' }),
    root: null,
  };
  return ctx;
}

async function scenario(options = {}) {
  const log = [];
  globalThis.confirm = (text) => {
    log.push({ confirm: text.split('\n')[0] });
    return options.confirm !== false;
  };
  globalThis.alert = (text) => { log.push({ alert: text.split('\n')[0] }); };

  const ctx = makeContext(log, options);
  await page._resetAndDetect(ctx);
  const state = { pending: !!page._detectPending, running: !!(ctx.state.plugAndPlay || {}).running };
  page.leave();                                  // stop the poll timer, so node can exit
  return { log, state };
}

console.log(JSON.stringify({
  normal: await scenario(),
  cancelled: await scenario({ confirm: false }),
  reconnecting: await scenario({ reloadPolls: 2 }),
  refused: await scenario({
    run: { started: false, reason: 'already_running', status: { running: true } } }),
}, null, 1));
"""


@unittest.skipUnless(NODE, 'node is not installed')
class TestRemoveAllAndSearchAgain(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'reset.mjs')
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write(SCRIPT)
            result = subprocess.run([NODE, path, FRONTEND], capture_output=True, text=True,
                                    timeout=120)
        if result.returncode != 0:
            raise AssertionError(f'node failed:\n{result.stderr}')
        cls.result = json.loads(result.stdout)

    def _commands(self, name):
        return [entry['ws'] for entry in self.result[name]['log'] if 'ws' in entry]

    def _dialogs(self, name):
        return [entry['confirm'] for entry in self.result[name]['log'] if 'confirm' in entry]

    def _alerts(self, name):
        return [entry['alert'] for entry in self.result[name]['log'] if 'alert' in entry]

    def test_one_dialog_asks_for_the_removal_and_the_search_together(self):
        dialogs = self._dialogs('normal')
        self.assertEqual(1, len(dialogs), f'expected a single question, got {dialogs}')
        self.assertIn('remove all 1 device(s) and search again', dialogs[0])

    def test_the_removal_is_followed_by_a_search(self):
        commands = self._commands('normal')
        self.assertIn('eltako/devices/remove_all', commands)
        self.assertIn('eltako/plug_and_play/run', commands)
        self.assertLess(commands.index('eltako/devices/remove_all'),
                        commands.index('eltako/plug_and_play/run'))

    def test_the_search_reads_the_bus_again(self):
        run = next(entry for entry in self.result['normal']['log']
                   if entry.get('ws') == 'eltako/plug_and_play/run')
        self.assertTrue(run['payload']['rescan_bus'])

    def test_the_page_shows_the_run_as_started_until_the_first_poll(self):
        # the backend answers before its task ran, so its status still says "not running"
        self.assertTrue(self.result['normal']['state']['running'])
        self.assertFalse(self.result['normal']['state']['pending'])

    def test_saying_no_removes_nothing_and_searches_nothing(self):
        self.assertEqual(1, len(self._dialogs('cancelled')))
        self.assertEqual([], self._commands('cancelled'))

    def test_the_search_waits_until_the_reloaded_gateways_are_back(self):
        log = self.result['reconnecting']['log']
        self.assertIn('eltako/plug_and_play/run', self._commands('reconnecting'))
        started = next(index for index, entry in enumerate(log)
                       if entry.get('ws') == 'eltako/plug_and_play/run')
        polls = [entry['gateways'] for entry in log[:started]
                 if entry.get('ws') == 'eltako/integration_info']
        self.assertGreater(len(polls), 1, 'the gateways were not waited for at all')
        self.assertEqual(1, polls[-1], 'the search started while the gateways were still reloading')

    def test_a_refused_search_is_reported_instead_of_a_progress_bar(self):
        self.assertIn('eltako/plug_and_play/run', self._commands('refused'))
        self.assertEqual(['A search is already running - its result appears here when it is done.'],
                         self._alerts('refused'))


if __name__ == '__main__':
    unittest.main()
