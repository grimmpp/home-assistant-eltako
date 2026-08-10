"""The reception page: the tool one walks through the building with.

The backend delivers the numbers (see test_reception.py); this pins what the page makes of
them, because that is what decides whether the tool is usable while walking:

* one card per gateway with the value one watches - dBm, quality and the repeater share
* one row per link, so a transmitter which two gateways hear can be compared at a glance
* **save this spot**: the current reading is kept under a name and survives a reload, because
  two positions cannot be compared from memory
* the window and the "watch one transmitter" filter reach the backend - a short window is what
  makes the reading follow the movement

Node is only used as a javascript engine; the test is skipped when node is not installed.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

from tests.frontend_dom_stub import DOM_STUB

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND = os.path.join(REPO, 'custom_components', 'eltako', 'frontend')
NODE = shutil.which('node')

SCRIPT = DOM_STUB + r"""
const { page } = await import(`${process.argv[2]}/pages/reception.js`);

const True_ = true, False_ = false;
const stored = {};
globalThis.window = {
  eltakoStandalone: False_,
  localStorage: {
    getItem: (key) => (key in stored ? stored[key] : null),
    setItem: (key, value) => { stored[key] = value; },
  },
};
globalThis.requestAnimationFrame = (callback) => setTimeout(callback, 0);
globalThis.confirm = () => True_;

const link = (overrides = {}) => ({
  address: 'FF-EE-DD-CC', name: 'Kitchen button', known: True_, gateway_id: 1,
  gateway_name: 'FAM-USB', count: 12, repeated: 0, repeated_share: 0, per_minute: 12,
  last_seen: '2026-08-10T12:00:00+00:00',
  rssi: { last: -62, avg: -63.5, min: -70, max: -58, count: 12 }, quality: 'good',
  ...overrides,
});

const survey = {
  recording: True_, window_seconds: 60, telegrams: 20, has_rssi: True_,
  buffer_limited: False_, covers_from: '2026-08-10T11:00:00+00:00',
  links: [
    link(),
    link({ gateway_id: 2, gateway_name: 'USB300', rssi: { last: -90, avg: -89.0, min: -93,
           max: -85, count: 8 }, quality: 'weak', count: 8, repeated: 6, repeated_share: 0.75 }),
  ],
  gateways: [
    { gateway_id: 1, gateway_name: 'FAM-USB', telegrams: 12, senders: 1, repeated: 0,
      repeated_share: 0, per_minute: 12, rssi_avg: -63.5, quality: 'good', best: -58, worst: -70 },
    { gateway_id: 2, gateway_name: 'USB300', telegrams: 8, senders: 1, repeated: 6,
      repeated_share: 0.75, per_minute: 8, rssi_avg: -89.0, quality: 'weak', best: -85, worst: -93 },
  ],
};

function makeContext(options = {}) {
  const ctx = {
    hass: { states: {} },
    state: {
      logInfo: { enabled: options.recording === False_ ? False_ : True_ },
      reception: options.survey === undefined ? survey : options.survey,
      receptionWindow: 60, receptionAddress: null,
      receptionSpots: options.spots || [],
    },
    api: {
      calls: [],
      lastError: null,
      async call(type, payload) {
        this.calls.push({ type, payload });
        return survey;
      },
    },
    root: null,
    requestRender() {}, requestContentRender() {},
    renderRecordingDisabled: () => '<div class="empty">recording is off</div>',
    async loadLogInfo() {}, async loadStatistics() {},
  };
  return ctx;
}

function show(ctx) {
  const root = parseHtml(page.render(ctx));
  ctx.root = root;
  page.afterRender(ctx, root);
  const toolbar = parseHtml(page.renderToolbar(ctx));
  // the shell renders the toolbar into the same tree - the page looks it up by id
  for (const child of [...toolbar.children]) root.append(child);
  page.bindToolbar(ctx, root);
  return root;
}

const ctx = makeContext();
const root = show(ctx);

const cards = root.querySelectorAll('.survey-card').map((card) => ({
  name: card.querySelector('.survey-name').textContent.trim(),
  value: card.querySelector('.survey-value').textContent.replace(/\s+/g, ' ').trim(),
  quality: (card.querySelector('.quality-tag') || { textContent: '' }).textContent.trim(),
  warn: card.classes.has('warn'),
  notes: card.querySelectorAll('.survey-note').map((note) => note.textContent.replace(/\s+/g, ' ').trim()),
}));

// save the current reading under a name, as one does in every room
root.getElementById('spot-name').attributes.value = 'Hallway';
root.getElementById('spot-name').value = 'Hallway';
await root.getElementById('save-spot').click();
const spotsAfterSave = ctx.state.receptionSpots;

// ... and it is on the page and in the browser
const withSpots = parseHtml(page.render(ctx));
const spotRows = withSpots.querySelectorAll('tbody tr')
  .filter((row) => row.textContent.includes('Hallway'));

// the window and the watched transmitter reach the backend
const filterCtx = makeContext();
const filterRoot = show(filterCtx);
const addressSelect = filterRoot.getElementById('reception-address');
addressSelect.value = 'FF-EE-DD-CC';
await addressSelect.listeners.change[0]({ target: { value: 'FF-EE-DD-CC' } });
const windowSelect = filterRoot.getElementById('reception-window');
await windowSelect.listeners.change[0]({ target: { value: '900' } });

const limitedRoot = parseHtml(page.render(makeContext({
  survey: { ...survey, buffer_limited: True_ } })));

console.log(JSON.stringify({
  cards,
  linkRows: root.querySelectorAll('.table-wrapper tbody tr').map((row) =>
    row.querySelectorAll('td').map((cell) => cell.textContent.replace(/\s+/g, ' ').trim())),
  addressOptions: filterRoot.querySelectorAll('#reception-address option')
    .map((option) => option.getAttribute('value')),
  savedSpot: spotsAfterSave.map((spot) => ({
    name: spot.name, window: spot.window_seconds,
    gateways: spot.gateways.map((gateway) => gateway.gateway_name),
    links: spot.links.length,
  })),
  storedSpots: JSON.parse(stored['eltako-reception-spots'] || '[]').length,
  spotOnPage: spotRows.length,
  apiCalls: filterCtx.api.calls,
  bufferNote: limitedRoot.querySelector('.survey-hint').textContent.includes('reaches back to'),
  recordingOff: page.render(makeContext({ recording: False_ })),
  refreshMs: page.refreshMs,
  needsRecording: page.needsRecording,
}, null, 1));
"""


@unittest.skipUnless(NODE, 'node is not installed')
class TestTheReceptionPage(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'reception.mjs')
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write(SCRIPT)
            result = subprocess.run([NODE, path, FRONTEND], capture_output=True, text=True,
                                    timeout=120)
        if result.returncode != 0:
            raise AssertionError(f'node failed:\n{result.stderr}')
        cls.result = json.loads(result.stdout)

    def test_one_card_per_gateway_with_the_value_one_watches(self):
        cards = self.result['cards']
        self.assertEqual(2, len(cards))
        self.assertIn('FAM-USB', cards[0]['name'])
        self.assertIn('-63.5', cards[0]['value'])
        self.assertIn('dBm', cards[0]['value'])
        self.assertEqual('good', cards[0]['quality'])

    def test_a_weak_gateway_is_marked(self):
        weak = self.result['cards'][1]
        self.assertTrue(weak['warn'])
        self.assertEqual('weak', weak['quality'])

    def test_a_repeated_link_says_that_the_direct_path_does_not_carry(self):
        notes = ' '.join(self.result['cards'][1]['notes'])
        self.assertIn('75% repeated', notes)
        self.assertIn('direct path does not carry', notes)

    def test_one_row_per_link_with_its_numbers(self):
        rows = self.result['linkRows']
        self.assertEqual(2, len(rows))
        first = rows[0]
        self.assertIn('FF-EE-DD-CC', first[0])
        self.assertIn('Kitchen button', first[0])
        self.assertEqual('FAM-USB', first[1])
        self.assertIn('good', first[2])
        self.assertEqual('-62', first[3])          # last
        self.assertEqual('-63.5', first[4])        # average
        self.assertEqual('-70 / -58', first[5])    # min / max
        self.assertIn('12', first[6])

    def test_the_second_gateway_of_the_same_transmitter_is_its_own_row(self):
        self.assertEqual('USB300', self.result['linkRows'][1][1])
        self.assertIn('75%', self.result['linkRows'][1][7])

    ### walking around

    def test_saving_a_spot_keeps_the_whole_reading_under_its_name(self):
        spots = self.result['savedSpot']
        self.assertEqual(1, len(spots))
        self.assertEqual('Hallway', spots[0]['name'])
        self.assertEqual(60, spots[0]['window'])
        self.assertEqual(['FAM-USB', 'USB300'], spots[0]['gateways'])
        self.assertEqual(2, spots[0]['links'])

    def test_a_spot_survives_a_reload(self):
        self.assertEqual(1, self.result['storedSpots'])

    def test_the_spots_are_on_the_page_to_compare_them(self):
        self.assertTrue(self.result['spotOnPage'])

    def test_the_watched_transmitter_and_the_window_reach_the_backend(self):
        calls = [call for call in self.result['apiCalls']
                 if call['type'] == 'eltako/reception/survey']
        self.assertEqual([{'window': 60, 'address': 'FF-EE-DD-CC'},
                          {'window': 900, 'address': 'FF-EE-DD-CC'}],
                         [call['payload'] for call in calls])

    def test_every_heard_transmitter_can_be_watched(self):
        self.assertEqual(['', 'FF-EE-DD-CC'], self.result['addressOptions'])

    ### honesty about the data

    def test_a_survey_which_is_cut_off_by_the_buffer_says_so(self):
        self.assertTrue(self.result['bufferNote'])

    def test_without_recording_the_page_explains_instead_of_measuring(self):
        self.assertIn('recording is off', self.result['recordingOff'])
        self.assertTrue(self.result['needsRecording'])

    def test_it_refreshes_by_itself_while_one_walks(self):
        self.assertLessEqual(self.result['refreshMs'], 5000)


class TestThePageIsPartOfThePanel(unittest.TestCase):

    def test_the_shell_loads_it(self):
        with open(os.path.join(FRONTEND, 'eltako-panel.js'), encoding='utf-8') as handle:
            source = handle.read()
        self.assertIn('pages/reception.js', source)
        self.assertIn('receptionPage', source)


if __name__ == '__main__':
    unittest.main()
