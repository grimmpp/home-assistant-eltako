"""Parallel bus scans are shown one below the other, not as one average.

Reading an RS485 bus takes minutes, and the buses are read at the same time: plug & play scans
every bus in parallel, and on the device page each gateway has its own scan button. The
progress used to be a single bar over the average of all of them - which says nothing about
the bus that is stuck, and nothing about how many are running at all.

This test pins that every scan keeps its own row, in all three places where a scan is visible
(the plug & play run on the overview, the search of the simple view, the bus sections of the
device page) and that the rows can be patched in place while a scan runs.

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
const frontend = process.argv[2];
const busScan = await import(`${frontend}/lib/bus_scan.js`);
const { page: overview } = await import(`${frontend}/pages/overview.js`);
const { page: home } = await import(`${frontend}/pages/home.js`);
const { page: devices } = await import(`${frontend}/pages/devices_config.js`);

/** two buses being read at the same time, at different points of their scan */
const SCANS = [
  { gateway_id: 1, positions_total: 14, positions_done: 2, position: 3,
    memory_rows_read: 23, memory_rows_total: 56, percent: 17 },
  { gateway_id: 2, positions_total: 8, positions_done: 6, position: 7,
    memory_rows_read: null, memory_rows_total: null, percent: 75 },
];
// `type` is what the device page reads to tell a bus gateway from a wireless one
const GATEWAYS = [{ id: 1, name: 'FAM14', type: 'fam14', base_id: 'FF-AA-80-00', connected: true },
                  { id: 2, name: 'FGW14-USB', type: 'fgw14usb', base_id: 'FF-AA-90-00', connected: true }];

/** what a rendered row says - one entry per scan, in the order they appear */
function rowsOf(html) {
  return parseHtml(html).querySelectorAll('.bus-scan[data-scan-gateway]').map((row) => ({
    gateway: row.getAttribute('data-scan-gateway'),
    name: (row.querySelector('.bus-scan-name') || { textContent: '' }).textContent.trim(),
    step: row.querySelector('.bus-scan-step').textContent.trim(),
    percent: row.querySelector('.bus-scan-percent').textContent.trim(),
    width: row.querySelector('.bus-scan-bar i').attributes.style,
  }));
}

/* ------------------------------------------------------- the shared component */

const nameOf = (id) => (GATEWAYS.find((gateway) => String(gateway.id) === String(id)) || {}).name;
const component = rowsOf(busScan.renderBusScans(SCANS, nameOf));
const empty = busScan.renderBusScans([], nameOf);
const withoutNames = rowsOf(busScan.renderBusScans(SCANS));

/* ---------------------------------------------------------- patching in place */

const live = parseHtml(busScan.renderBusScans(SCANS, nameOf));
const patched = busScan.applyBusScans(live, [
  { ...SCANS[0], positions_done: 9, memory_rows_read: 4, memory_rows_total: 12, percent: 68 },
  SCANS[1],
]);
const afterPatch = live.querySelectorAll('.bus-scan[data-scan-gateway="1"]').map((row) => ({
  step: row.querySelector('.bus-scan-step').textContent.trim(),
  percent: row.querySelector('.bus-scan-percent').textContent.trim(),
}))[0];
// one scan finished: the rows no longer match the running scans, so the page has to render
const stale = busScan.applyBusScans(live, [SCANS[1]]);

/* ------------------------------------------------------------------ the pages */

const pnp = {
  enabled: true, running: true, stage: 'bus', step: 'Reading the bus', stages: ['ports', 'bus', 'devices'],
  bus_scans: SCANS, started_at: '2026-08-10T10:00:00', last_run: null, interval: 1440,
  last_report: { started_at: '2026-08-10T10:00:00', gateways_added: [], gateways_suggested: [],
                 devices_added: [], devices_skipped: [], buses_read: [], warnings: [] },
};

const overviewCtx = {
  state: { integrationInfo: { gateways: GATEWAYS, entities: {}, general_settings: {} },
           plugAndPlay: pnp, logInfo: {}, statistics: { summary: {}, devices: [], unknown_devices: [] },
           gatewayForm: null, gatewayEditor: null, configuredDevices: [] },
  api: { call: async () => null, lastError: null },
  root: null, requestRender() {}, requestContentRender() {},
};
const overviewRows = rowsOf(overview._renderRunningBar(overviewCtx, pnp));

const homeCtx = {
  hass: { states: {} },
  state: { integrationInfo: { gateways: GATEWAYS }, plugAndPlay: pnp, configuredDevices: [],
           statistics: { devices: [], unknown_devices: [] }, simpleFilter: '', simpleEditor: null,
           deviceForm: null },
  api: { call: async () => null, lastError: null },
  root: null, requestRender() {}, requestContentRender() {},
};
const homeHtml = home._renderDetection(homeCtx);
const homeRows = rowsOf(homeHtml);

// the device page: one section per gateway, so the scans are below each other anyway - each
// section shows the progress of its own bus
const devicesCtx = {
  state: {
    integrationInfo: { gateways: GATEWAYS },
    configuredDevices: [],
    busMembers: {
      members: [], hint: '',
      scans_running: { '1': true, '2': true },
      busy_with: { '1': 'bus scan', '2': 'bus scan' },
      scan_progress: { '1': SCANS[0], '2': SCANS[1] },
    },
    statistics: { devices: [], unknown_devices: [] },
    deviceForm: null, editor: null, configFilter: '', configSort: 'address',
    configSortDescending: false, deviceView: 'hierarchy', onlySilent: false, memoryPanel: null,
  },
  api: { call: async () => null, lastError: null },
  root: null, requestRender() {}, requestContentRender() {},
};
const devicesHtml = devices.render(devicesCtx);
const devicesRows = rowsOf(devicesHtml);

console.log(JSON.stringify({
  component, empty, withoutNames, patched, afterPatch, stale,
  overviewRows, homeRows, homeHtml, devicesRows,
  devicesHasLeave: typeof devices.leave === 'function',
}, null, 1));
"""


@unittest.skipUnless(NODE, 'node is not installed')
class TestParallelBusScansAreListed(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'scans.mjs')
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write(SCRIPT)
            result = subprocess.run([NODE, path, FRONTEND], capture_output=True, text=True,
                                    timeout=120)
        if result.returncode != 0:
            raise AssertionError(f'node failed:\n{result.stderr}')
        cls.result = json.loads(result.stdout)

    def test_every_scan_gets_its_own_row(self):
        rows = self.result['component']
        self.assertEqual(['1', '2'], [row['gateway'] for row in rows])
        self.assertEqual(['FAM14', 'FGW14-USB'], [row['name'] for row in rows])

    def test_a_row_names_the_position_and_the_memory_it_is_reading(self):
        first, second = self.result['component']
        # the position being read is done + 1 - the same wording as bus_members.py
        self.assertEqual('position 3/14 · memory 23/56', first['step'])
        self.assertEqual('17%', first['percent'])
        # a position without a memory read yet only reports the position
        self.assertEqual('position 7/8', second['step'])
        self.assertEqual('75%', second['percent'])

    def test_every_row_has_its_own_bar(self):
        self.assertEqual(['width:17%', 'width:75%'],
                         [row['width'] for row in self.result['component']])

    def test_nothing_is_rendered_without_a_running_scan(self):
        self.assertEqual('', self.result['empty'])

    def test_the_name_is_left_out_where_it_already_stands_above(self):
        self.assertEqual(['', ''], [row['name'] for row in self.result['withoutNames']])

    def test_a_running_scan_is_patched_in_place(self):
        self.assertTrue(self.result['patched'])
        self.assertEqual('position 10/14 · memory 4/12', self.result['afterPatch']['step'])
        self.assertEqual('68%', self.result['afterPatch']['percent'])

    def test_a_finished_scan_asks_for_a_new_render(self):
        self.assertFalse(self.result['stale'])

    def test_the_plug_and_play_run_lists_both_buses(self):
        self.assertEqual(['FAM14', 'FGW14-USB'],
                         [row['name'] for row in self.result['overviewRows']])
        self.assertEqual(['17%', '75%'], [row['percent'] for row in self.result['overviewRows']])

    def test_the_simple_view_has_no_progress_bar_of_its_own(self):
        """The activity banner of the panel stands directly above this card and already shows
        every running bus scan with its counters. A second, nearly identical bar a few pixels
        below it does not add information - it makes one operation look like two."""
        self.assertEqual([], self.result['homeRows'])

    def test_the_simple_view_still_says_what_is_going_on(self):
        """Dropping the bar must not drop the words: this card is the only place which says
        that the devices do not react meanwhile and how many were found so far."""
        html = self.result['homeHtml']

        self.assertIn('Searching for devices', html)
        self.assertIn('the 2 buses', html)
        self.assertIn('do not react meanwhile', html)

    def test_the_device_page_shows_the_progress_of_every_bus_section(self):
        self.assertEqual(['1', '2'], [row['gateway'] for row in self.result['devicesRows']])
        self.assertEqual(['position 3/14 · memory 23/56', 'position 7/8'],
                         [row['step'] for row in self.result['devicesRows']])

    def test_the_device_page_stops_its_poll_when_it_is_left(self):
        self.assertTrue(self.result['devicesHasLeave'])


if __name__ == '__main__':
    unittest.main()
