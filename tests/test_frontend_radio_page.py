"""The radio comparison page (frontend/pages/radio.js).

The page answers "did all my gateways receive the same telegram - and did they read it the same
way?", and everything it claims has to be readable in its markup:

* the reception rate and the signal strength per gateway,
* the gateway which received nothing at all (it is missing from the backend report and would
  silently disappear),
* the byte which differs from what the others reported, and the values a gateway made of it,
* whether a device arrives directly or through a repeater,
* the head to head table of two gateways,
* and the controls: the window, the views with their counts, the gateway and sender selection -
  each of them has to reach the backend, because the analysis is computed there.

Rendered with node into the dom stub, like the other page tests - the frontend has no build
step and no javascript test runner.
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
const { page } = await import(`${process.argv[2]}/pages/radio.js`);
const report = JSON.parse(readFileSyncShim(process.argv[3]));

/** every call the page made to the backend, so the controls can be checked */
const calls = [];

function makeContext(overrides = {}) {
  return {
    state: {
      logInfo: { enabled: true },
      // three gateways are configured, the third one has never received anything
      integrationInfo: { gateways: [
        { id: 1, name: 'USB300 hall', simulated: false },
        { id: 2, name: 'MGW cellar', simulated: false },
        { id: 3, name: 'USB300 attic', simulated: false },
      ] },
      radioComparison: report,
      radioFilter: '',
      radioWindowMs: 200,
      radioView: 'all',
      radioGateways: [],
      radioSender: null,
      radioOpen: {},
      ...overrides,
    },
    api: {
      call: async (type, payload) => { calls.push({ type, payload }); return report; },
      lastError: null,
    },
    root: null,
    requestRender() {}, requestContentRender() {},
    // the shell provides these; the page loads the log info and the gateways through them
    loadLogInfo: async () => ({ enabled: true }),
    loadIntegrationInfo: async () => ({}),
    // the shell renders this when the telegram recording is switched off
    renderRecordingDisabled: () => '<div class="notice warn">recording is disabled</div>',
  };
}

function show(ctx) {
  const root = parseHtml(page.render(ctx));
  ctx.root = root;
  page.afterRender(ctx, root);
  return root;
}

const ctx = makeContext();
const root = show(ctx);
const text = root.textContent;
const clean = (value) => value.replace(/\s+/g, ' ').trim();

const rowsOf = (table) => table.querySelectorAll('tbody tr');
const tables = root.querySelectorAll('table');
const gatewayTable = tables[0];
const gatewayRows = rowsOf(gatewayTable).map((row) => ({
  name: clean(row.querySelector('.gateway-name span').textContent),
  cells: row.querySelectorAll('td').map((cell) => clean(cell.textContent)),
  paths: row.querySelectorAll('.path').map((path) => clean(path.textContent)),
}));

// gateway against gateway
const pairTable = tables[1];
const pairRows = rowsOf(pairTable).map((row) =>
  row.querySelectorAll('td').map((cell) => clean(cell.textContent)));

// the "who receives what" matrix: one column per gateway
const matrix = root.querySelector('table.matrix');
const matrixHead = matrix.querySelectorAll('thead th').map((th) => clean(th.textContent));
const matrixRow = rowsOf(matrix)[0].querySelectorAll('td').map((cell) => ({
  text: clean(cell.textContent),
  classes: cell.attributes.class || '',
  paths: cell.querySelectorAll('.path').map((path) => clean(path.textContent)),
}));

// the burst list and the marked byte inside the unfolded detail
const burstTable = root.querySelector('table.clickable');
const burstRows = rowsOf(burstTable).filter((row) => (row.attributes['data-burst'] || '') !== '');
const markedBytes = root.querySelectorAll('.byte-diff').map((element) => element.textContent);
const detailHead = root.querySelector('.burst-detail table').querySelectorAll('th')
  .map((th) => clean(th.textContent));

// the colours: which telegram row is red, which one is yellow, which one is plain
const burstColours = burstRows.map((row) => ({
  address: row.querySelectorAll('td')[1].textContent.trim(),
  difference: clean(row.querySelectorAll('td')[5].textContent),
  classes: row.attributes.class || '',
}));
// and the gateway which deviates inside the unfolded detail
const detailColours = root.querySelectorAll('.burst-detail tr').map((row) => ({
  gateway: clean((row.querySelectorAll('td')[0] || { textContent: '' }).textContent),
  classes: row.attributes.class || '',
  markedCells: row.querySelectorAll('td.issue').length,
}));

// clicking a row remembers that its detail is open, so a reload cannot close it
await burstRows[0].click();
const remembered = Object.keys(ctx.state.radioOpen);

// the controls: every one of them has to reach the backend
const viewButtons = root.querySelectorAll('button[data-view]').map((button) => clean(button.textContent));
await root.querySelector('button[data-view="disagreeing"]').click();
const viewCall = calls[calls.length - 1];
const viewState = ctx.state.radioView;

await root.querySelector('button[data-gateway="2"]').click();
const gatewayCall = calls[calls.length - 1];
const gatewayState = [...ctx.state.radioGateways];

await root.querySelector('button[data-sender]').click();
const senderCall = calls[calls.length - 1];
const senderState = ctx.state.radioSender;

/**
 * The page reloads itself every four seconds while the user clicks a view.
 *
 * Both requests are in flight at the same time, and the periodic one was sent with the *old*
 * view. If its answer arrives last and is simply stored, the table jumps back to everything -
 * which looks exactly like "the filter does not work".
 */
const raceCtx = makeContext();
const answers = [];
raceCtx.api.call = (type, payload) => new Promise((resolve) => {
  answers.push(() => resolve({ ...report, summary: { ...report.summary, filter: payload.filter },
                               bursts: payload.filter === 'all' ? report.bursts
                                                                : report.bursts.slice(0, 1) }));
});
const raceRoot = parseHtml(page.render(raceCtx));
raceCtx.root = raceRoot;
page.afterRender(raceCtx, raceRoot);

const periodic = page.load(raceCtx);                       // the 4 s refresh, view 'all'
await raceRoot.querySelector('button[data-view="disagreeing"]').click();  // the user
answers[answers.length - 1]();                             // the click answers first
await new Promise((resolve) => setTimeout(resolve, 0));
answers[0]();                                              // the stale refresh answers last
await periodic;
await new Promise((resolve) => setTimeout(resolve, 0));
const afterRace = {
  view: raceCtx.state.radioView,
  filter: (raceCtx.state.radioComparison.summary || {}).filter,
  bursts: (raceCtx.state.radioComparison.bursts || []).length,
};

/**
 * The page follows the live telegram stream instead of a timer.
 *
 * setTimeout is captured so the scheduling can be checked without waiting for it: one
 * transmission arrives as one event per gateway, and all of them have to share a single
 * analysis - which must not run before the window of that transmission has passed.
 */
const scheduled = [];
const realTimeout = globalThis.setTimeout;
globalThis.setTimeout = (callback, delay) => { scheduled.push({ callback, delay }); return scheduled.length; };
globalThis.clearTimeout = () => {};

const eventCtx = makeContext();
const eventCalls = [];
eventCtx.api.call = async (type, payload) => { eventCalls.push(payload); return report; };
const telegram = (overrides = {}) => ({ address: 'FE-DC-BA-98', gateway_id: 1,
                                        msg_type: 'RPSMessage', ...overrides });

// three gateways report the same transmission: one analysis, not three
page.onTelegram(eventCtx, telegram({ gateway_id: 1 }));
page.onTelegram(eventCtx, telegram({ gateway_id: 2 }));
page.onTelegram(eventCtx, telegram({ gateway_id: 3 }));
const events = { scheduledCount: scheduled.length, delay: scheduled[0] ? scheduled[0].delay : null };
await scheduled[0].callback();
events.calls = eventCalls.length;

// telegrams which cannot change what is shown do not trigger anything
scheduled.length = 0;
page.onTelegram(eventCtx, { address: 'bus 5', role: 'bus_message', gateway_id: 1 });
page.onTelegram(eventCtx, telegram({ address: null }));
// what a gateway read off its RS485 wire is no radio reception either
page.onTelegram(eventCtx, telegram({ address: 'FF-AA-BB-05', local_address: '00-00-00-05',
                                     direction: 'incoming' }));
events.ignoredBus = scheduled.length;

// ... but what a bus gateway *sent* goes on air, so it is part of the comparison
page.onTelegram(eventCtx, telegram({ address: 'FF-AA-BB-05', local_address: '00-00-00-05',
                                     direction: 'outgoing' }));
events.acceptedOutgoingBus = scheduled.length;
// the pending analysis must not swallow the telegrams of the restriction check below
page._cancelScheduledReload();
scheduled.length = 0;

// ... and neither do telegrams outside the current restriction
const restricted = makeContext({ radioSender: 'FE-DC-BA-98', radioGateways: ['1'] });
restricted.api.call = async () => report;
page.onTelegram(restricted, telegram({ address: '01-23-45-67' }));
page.onTelegram(restricted, telegram({ gateway_id: 2 }));
events.ignoredRestricted = scheduled.length;
page.onTelegram(restricted, telegram({ gateway_id: 1 }));
events.acceptedRestricted = scheduled.length;

// leaving the page must not leave a timer behind
page.leave(restricted);
events.hasTimer = !!page._reloadTimer;
globalThis.setTimeout = realTimeout;

/**
 * "Where the differences are": the groups, and where each difference happens.
 *
 * Rendered from a second report with *three* gateways - only a real majority can name the
 * gateway which reported something else, and with two there is nobody to name.
 */
const outlier = JSON.parse(readFileSyncShim(process.argv[4]));
const outlierRoot = parseHtml(page.render(makeContext({ radioComparison: outlier })));
const diffRows = rowsOf(outlierRoot.querySelector('table.diff-table')).map((row) => ({
  group: (row.attributes.class || '').includes('group'),
  cells: row.querySelectorAll('td').map((cell) => clean(cell.textContent)),
  senders: row.querySelectorAll('button[data-sender]')
    .map((button) => button.attributes['data-sender']),
  view: ((row.querySelector('button[data-view]') || { attributes: {} })
    .attributes['data-view']) || '',
}));
const countBars = outlierRoot.querySelectorAll('.count-bars .meter span')
  .map((span) => span.attributes.style);

// the window select of the toolbar
const toolbar = parseHtml(page.renderToolbar(makeContext()));
const windowOptions = toolbar.querySelectorAll('#radio-window option')
  .map((option) => option.attributes.value);

// the sender options are patched into the toolbar select after a report arrived
const toolbarCtx = makeContext();
const toolbarRoot = parseHtml(page.renderToolbar(toolbarCtx) + page.render(toolbarCtx));
page.afterRender(toolbarCtx, toolbarRoot);
const senderOptions = toolbarRoot.querySelectorAll('#radio-sender option')
  .map((option) => clean(option.textContent));

// a filter which matches nothing empties the lists instead of throwing
const noMatch = show(makeContext({ radioFilter: 'does-not-exist' }));

// recording switched off: the page explains it instead of rendering empty tables
const disabled = page.render(makeContext({ logInfo: { enabled: false } }));

// nothing recorded yet
const empty = page.render(makeContext({ radioComparison: null }));

// only one gateway ever received something: the page says why it cannot compare
const alone = page.render(makeContext({ radioComparison: {
  ...report,
  gateways: [report.gateways[0]],
  pairs: [],
  summary: { ...report.summary, gateway_count: 1 },
} }));

console.log(JSON.stringify({
  gatewayRows,
  pairRows,
  matrixHead,
  matrixRow,
  burstCount: burstRows.length,
  burstColours,
  detailColours,
  markedBytes,
  detailHead,
  remembered,
  viewButtons,
  viewCall, viewState,
  gatewayCall, gatewayState,
  senderCall, senderState,
  afterRace,
  events,
  diffRows,
  countBars,
  windowOptions,
  senderOptions,
  noMatchText: noMatch.textContent,
  status: page.renderStatus(ctx),
  hasDisabledHint: disabled.includes('recording is disabled'),
  emptyText: empty,
  aloneText: alone,
  fullText: text,
}, null, 1));
"""

# the dom stub has no fs helper - the report is read with a tiny shim in front of the script
SHIM = r"""
import { readFileSync } from 'fs';
const readFileSyncShim = (path) => readFileSync(path, 'utf-8');
"""


def build_report() -> dict:
    """A report of the real backend: five telegrams with everything the page shows."""
    from custom_components.eltako.observation.radio_comparison import RadioComparison
    from tests.test_radio_comparison import BASE_MS, record

    comparison = RadioComparison()
    # heard by both gateways, identically
    comparison.add(record(1, 1, BASE_MS, rssi=-61, decoded={'button_pressed': True}))
    comparison.add(record(2, 2, BASE_MS + 7, rssi=-83, decoded={'button_pressed': True}))
    # gateway 2 reports a different data byte - this is what the page is for
    comparison.add(record(3, 1, BASE_MS + 10_000, data='70', rssi=-62,
                          decoded={'button_pressed': True}))
    comparison.add(record(4, 2, BASE_MS + 10_006, data='50', rssi=-91,
                          decoded={'button_pressed': False}))
    # only gateway 1 hears it, gateway 2 misses it
    comparison.add(record(5, 1, BASE_MS + 20_000, rssi=-63))
    # gateway 2 only gets it through a repeater
    comparison.add(record(6, 1, BASE_MS + 30_000, rssi=-60))
    comparison.add(record(7, 2, BASE_MS + 30_050, status='0x31', rp_count=1, rssi=-88))
    # a second sender, so the sender selection has something to offer
    comparison.add(record(8, 1, BASE_MS + 40_000, address='01-23-45-67', rssi=-70))
    return comparison.get_report()


def build_outlier_report() -> dict:
    """A report with *three* gateways, one of which is the odd one out.

    "Where the differences are" can only name a gateway when there is a majority to be the odd
    one out of - with two gateways reporting two values nobody can be blamed (see `compare()`),
    which is exactly what the report above shows. Both cases have to be readable.
    """
    from custom_components.eltako.observation.radio_comparison import RadioComparison
    from tests.test_radio_comparison import BASE_MS, record

    comparison = RadioComparison()
    # all three agree
    comparison.add(record(1, 1, BASE_MS, rssi=-60))
    comparison.add(record(2, 2, BASE_MS + 5, rssi=-75))
    comparison.add(record(3, 3, BASE_MS + 9, rssi=-86))
    # gateway 3 reports another data byte than the two others - twice
    for index, offset in enumerate((10_000, 20_000)):
        comparison.add(record(index * 3 + 4, 1, BASE_MS + offset, data='70', rssi=-61))
        comparison.add(record(index * 3 + 5, 2, BASE_MS + offset + 5, data='70', rssi=-76))
        comparison.add(record(index * 3 + 6, 3, BASE_MS + offset + 9, data='50', rssi=-88))
    # a second device which one gateway only hears over a repeater
    comparison.add(record(10, 1, BASE_MS + 30_000, address='01-23-45-67', rssi=-70))
    comparison.add(record(11, 2, BASE_MS + 30_040, address='01-23-45-67',
                          status='0x31', rp_count=1, rssi=-84))
    return comparison.get_report()


@unittest.skipUnless(NODE, 'node is not installed - the page cannot be rendered here')
class TestRadioPage(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        script = os.path.join(cls.tmp.name, 'radio.mjs')
        report = os.path.join(cls.tmp.name, 'report.json')
        outlier = os.path.join(cls.tmp.name, 'outlier.json')
        with open(script, 'w', encoding='utf-8') as handle:
            handle.write(SHIM + SCRIPT)
        with open(report, 'w', encoding='utf-8') as handle:
            json.dump(build_report(), handle)
        with open(outlier, 'w', encoding='utf-8') as handle:
            json.dump(build_outlier_report(), handle)

        env = os.environ.copy()
        env['LC_ALL'] = 'C.UTF-8'
        env['LANG'] = 'C.UTF-8'
        process = subprocess.run([NODE, script, FRONTEND, report, outlier],
                                 capture_output=True, text=True, env=env, timeout=120, cwd=REPO)
        assert process.returncode == 0, f"node failed:\n{process.stderr[-3000:]}"
        cls.result = json.loads(process.stdout)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def gateway(self, name: str) -> dict:
        return next(row for row in self.result['gatewayRows'] if row['name'] == name)

    ### per gateway ---------------------------------------------------------

    def test_every_configured_gateway_has_a_row(self):
        """The gateway which received nothing is not in the backend report - and it is the
        one worth seeing, so the configured gateways are the base of the table."""
        names = [row['name'] for row in self.result['gatewayRows']]

        self.assertEqual(names, ['USB300 hall', 'MGW cellar', 'USB300 attic'])

    def test_the_reception_rate_is_shown_per_gateway(self):
        # gateway 1 received all five, gateway 2 three of them
        self.assertIn('5 of 5', self.gateway('USB300 hall')['cells'][1])
        self.assertIn('100 %', self.gateway('USB300 hall')['cells'][2])
        self.assertIn('3 of 5', self.gateway('MGW cellar')['cells'][1])
        self.assertIn('60 %', self.gateway('MGW cellar')['cells'][2])
        self.assertEqual(self.gateway('MGW cellar')['cells'][3], '2')

    def test_the_signal_strength_is_shown_per_gateway(self):
        self.assertIn('-63.2 dBm', self.gateway('USB300 hall')['cells'][-1])
        self.assertIn('-60 dBm', self.gateway('USB300 hall')['cells'][-1])   # the best one
        self.assertIn('-87.3 dBm', self.gateway('MGW cellar')['cells'][-1])

    def test_the_path_is_shown_per_gateway(self):
        """Directly out of the air, or through a repeater - one tag per path with its count."""
        self.assertEqual(self.gateway('USB300 hall')['paths'], ['direct 5'])
        self.assertEqual(self.gateway('MGW cellar')['paths'], ['direct 2', 'L1 1'])

    ### gateway against gateway --------------------------------------------

    def test_two_gateways_are_compared_head_to_head(self):
        row = self.result['pairRows'][0]

        self.assertIn('USB300 hall', row[0])
        self.assertIn('MGW cellar', row[0])
        self.assertIn('3 of 5', row[1])     # both received three of the five
        self.assertEqual(row[2], '2')       # only gateway 1
        self.assertEqual(row[3], '0')       # only gateway 2
        # of the three both received: one differed, the other two were identical (the
        # repeater hop of the third one is not a disagreement)
        self.assertEqual(row[5], '1 2 identical')
        self.assertEqual(row[7], '1')       # one arrived over a different path

    def test_the_pair_says_which_one_hears_better(self):
        row = self.result['pairRows'][0]

        self.assertIn('dB', row[-1])
        self.assertIn('USB300 hall is stronger', row[-1])

    ### which gateway receives which device --------------------------------

    def test_the_matrix_has_a_column_per_gateway(self):
        head = " | ".join(self.result['matrixHead'])

        for name in ('USB300 hall', 'MGW cellar', 'USB300 attic'):
            self.assertIn(name, head)

    def test_a_gateway_which_never_heard_an_address_is_marked(self):
        """The empty cell is the point of the matrix - it must not look like a zero, and a
        problem is coloured instead of only worded."""
        silent = [cell for cell in self.result['matrixRow']
                  if cell['text'] in ('\u2013', '-')]

        self.assertEqual(len(silent), 1, msg=self.result['matrixRow'])
        self.assertIn('issue', silent[0]['classes'])
        # and the gateway which loses telegrams of that device is yellow, not red
        partial = [cell for cell in self.result['matrixRow'] if 'attention' in cell['classes']]
        self.assertEqual(len(partial), 1, msg=self.result['matrixRow'])

    def test_the_device_row_says_how_each_gateway_hears_it(self):
        """Direct or through a repeater, per device and per gateway."""
        cells = [cell for cell in self.result['matrixRow'] if cell['paths']]

        self.assertEqual(cells[0]['paths'], ['direct 4'])   # the busiest sender
        self.assertEqual(cells[1]['paths'], ['direct 2', 'L1 1'])

    ### where the differences are -------------------------------------------

    def groups(self) -> list:
        return [row for row in self.result['diffRows'] if row['group']]

    def diff(self, label: str) -> dict:
        return next(row for row in self.result['diffRows']
                    if not row['group'] and row['cells'][0].startswith(label))

    def test_the_differences_are_sorted_into_their_causes(self):
        """A wrong byte, a wrong reading and a repeater hop have nothing to do with each
        other - lumping them into one list makes the normal one look like a fault."""
        titles = [row['cells'][0] for row in self.groups()]

        self.assertEqual(len(titles), 2, msg=titles)
        self.assertTrue(titles[0].startswith('Received differently'), msg=titles[0])
        self.assertTrue(titles[1].startswith('Different path'), msg=titles[1])

    def test_every_group_can_show_its_telegrams(self):
        self.assertEqual([row['view'] for row in self.groups()], ['disagreeing', 'hops'])

    def test_a_difference_says_how_often_it_happened_and_how_much_of_everything_that_is(self):
        # two of the four transmissions had a differing data byte
        self.assertIn('2', self.diff('data bytes')['cells'][1])
        self.assertIn('50 % of 4', self.diff('data bytes')['cells'][1])

    def test_a_difference_names_the_device_it_happens_on(self):
        """The count alone only says "something is wrong somewhere" - the device it is wrong
        on is the answer, and it is a button which narrows the whole page down to it."""
        row = self.diff('data bytes')

        self.assertIn('Rocker switch', row['cells'][2])
        self.assertEqual(row['senders'], ['FE-DC-BA-98'])
        self.assertEqual(self.diff('repeater hops')['senders'], ['01-23-45-67'])

    def test_a_difference_names_the_gateway_which_reported_something_else(self):
        self.assertIn('GW3', self.diff('data bytes')['cells'][3])

    def test_the_page_says_how_many_gateways_heard_the_same_telegram(self):
        """As bars: "most of them" has to be readable without comparing numbers."""
        self.assertIn('How many gateways heard the same transmission', self.result['fullText'])
        self.assertTrue(self.result['countBars'], msg=self.result['countBars'])
        self.assertTrue(all('width' in style for style in self.result['countBars']))

    ### the single telegram ------------------------------------------------

    def test_the_burst_list_shows_the_recorded_telegrams(self):
        self.assertEqual(self.result['burstCount'], 5)
        self.assertIn('missing:', self.result['fullText'])

    def test_the_differing_byte_is_marked(self):
        self.assertEqual(self.result['markedBytes'], ['50'])

    def test_the_detail_says_what_each_gateway_made_of_the_telegram(self):
        """"Read as" and "Values": whether a gateway *interpreted* it differently."""
        head = " | ".join(self.result['detailHead'])

        self.assertIn('Read as', head)
        self.assertIn('Values', head)
        self.assertIn('button_pressed=False', self.result['fullText'])

    def test_a_problem_is_coloured_and_a_normal_difference_is_not(self):
        """With a table this wide the eye has to be able to jump to the row which is wrong:
        red for "not received or not read the same way", yellow for "somebody missed it", and
        nothing at all for a repeater hop - which is normal."""
        rows = self.result['burstColours']
        colour_of = lambda difference: [row['classes'] for row in rows        # noqa: E731
                                        if row['difference'] == difference]

        # the telegram whose data bytes and values differ is red
        self.assertEqual(colour_of('data bytes values'), ['issue'])
        # the one which only came in over a repeater is not a problem at all
        self.assertEqual(colour_of('repeater hops'), [''])
        # identical, but somebody did not get it: yellow. Identical and everybody had it: plain.
        self.assertEqual(sorted(colour_of('identical')), ['', 'attention', 'attention'])

    def test_the_gateway_which_deviates_is_marked_inside_the_telegram(self):
        """Not only the row: the cell which does not match is coloured, so "where" is one
        look and not a comparison by hand."""
        marked = [row for row in self.result['detailColours'] if row['classes'] == 'issue']

        self.assertTrue(marked, msg=self.result['detailColours'])
        self.assertTrue(any(row['markedCells'] for row in marked), msg=marked)

    def test_an_open_detail_is_remembered_across_the_refresh(self):
        self.assertEqual(len(self.result['remembered']), 1)
        # keyed by address and time, so it survives a report in which the row moved
        self.assertRegex(self.result['remembered'][0], r'^[0-9A-F-]+\|\d+$')

    ### the controls -------------------------------------------------------

    def test_every_view_is_offered_with_its_count(self):
        views = " | ".join(self.result['viewButtons'])

        for label in ('all', 'identical', 'received differently', 'read differently',
                      'repeater hop only', 'somebody missed it', 'only one gateway'):
            self.assertIn(label, views)
        # the counts come from the backend, so a view which holds nothing says so
        self.assertIn('received differently 1', views)

    def test_the_periodic_refresh_cannot_undo_the_chosen_view(self):
        """The page reloads every four seconds. A refresh which was sent with the previous view
        and answers *after* the click must not be stored - otherwise the table jumps back to
        everything a moment after the filter was chosen, which is indistinguishable from a
        filter which does not work at all."""
        self.assertEqual(self.result['afterRace']['view'], 'disagreeing')
        self.assertEqual(self.result['afterRace']['filter'], 'disagreeing')
        self.assertEqual(self.result['afterRace']['bursts'], 1)

    ### it follows the telegrams instead of a timer -------------------------

    def test_the_page_does_not_poll(self):
        """A poll would ask the same question over and over - and the whole analysis runs per
        request, so that is not free. The page reacts to the live stream instead."""
        import re

        source = open(os.path.join(FRONTEND, 'pages', 'radio.js'), encoding='utf-8').read()

        self.assertIsNone(re.search(r'^\s*refreshMs:', source, re.MULTILINE))
        self.assertIn('onTelegram(ctx, telegram)', source)

    def test_one_transmission_leads_to_one_analysis(self):
        """Three gateways receiving the same telegram are three events - and one question."""
        events = self.result['events']

        self.assertEqual(events['scheduledCount'], 1)
        self.assertEqual(events['calls'], 1)

    def test_the_analysis_waits_for_the_window_to_pass(self):
        """Asked earlier, the last gateway would still be about to report and the page would
        claim that it missed the telegram."""
        self.assertGreaterEqual(self.result['events']['delay'], 200)

    def test_a_telegram_which_changes_nothing_is_ignored(self):
        events = self.result['events']

        self.assertEqual(events['ignoredBus'], 0)
        self.assertEqual(events['ignoredRestricted'], 0)
        self.assertEqual(events['acceptedRestricted'], 1)

    def test_a_telegram_a_bus_gateway_sent_is_not_ignored(self):
        """It goes on air - the gateways which received it are exactly what this page shows."""
        self.assertEqual(self.result['events']['acceptedOutgoingBus'], 1)

    def test_leaving_the_page_drops_its_timer(self):
        self.assertFalse(self.result['events']['hasTimer'])

    def test_choosing_a_view_asks_the_backend_for_it(self):
        self.assertEqual(self.result['viewState'], 'disagreeing')
        self.assertEqual(self.result['viewCall']['type'], 'eltako/radio_comparison/report')
        self.assertEqual(self.result['viewCall']['payload']['filter'], 'disagreeing')

    def test_selecting_gateways_restricts_the_analysis(self):
        self.assertEqual(self.result['gatewayState'], ['2'])
        self.assertEqual(self.result['gatewayCall']['payload']['gateway_ids'], ['2'])

    def test_selecting_a_sender_restricts_the_analysis(self):
        self.assertEqual(self.result['senderState'], 'FE-DC-BA-98')
        self.assertEqual(self.result['senderCall']['payload']['address'], 'FE-DC-BA-98')

    def test_the_window_is_a_choice_of_the_toolbar(self):
        self.assertIn('50', self.result['windowOptions'])
        self.assertIn('200', self.result['windowOptions'])
        self.assertIn('2000', self.result['windowOptions'])

    def test_the_senders_of_the_recording_are_offered(self):
        options = " | ".join(self.result['senderOptions'])

        self.assertIn('all senders', options)
        self.assertIn('FE-DC-BA-98', options)
        self.assertIn('01-23-45-67', options)

    ### the states which are not the happy path ----------------------------

    def test_a_filter_without_a_match_does_not_break_the_page(self):
        self.assertIn('No telegram matches the text filter', self.result['noMatchText'])

    def test_recording_switched_off_is_explained(self):
        self.assertTrue(self.result['hasDisabledHint'])

    def test_nothing_recorded_yet_says_so(self):
        self.assertIn('Waiting for radio telegrams', self.result['emptyText'])

    def test_a_single_receiving_gateway_is_explained(self):
        """With one gateway there is nothing to compare - and that is a state a user can be
        in for a long time without understanding why the page stays empty."""
        self.assertIn('Only one gateway is receiving radio telegrams', self.result['aloneText'])

    def test_the_status_line_counts_the_differences(self):
        status = self.result['status']

        self.assertIn('5 telegrams compared', status)
        self.assertIn('1 received differently', status)
        self.assertIn('200 ms window', status)

    def test_no_placeholder_leaks_into_the_markup(self):
        for marker in ('undefined', 'NaN', '${'):
            self.assertNotIn(marker, self.result['fullText'])
