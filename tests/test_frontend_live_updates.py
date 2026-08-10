"""The simple view updates itself - it is not reloaded.

Pressing "off" on a card used to look dead: the page had a 15 second reload interval and only
that reload redrew the button, so the state changed somewhere between "immediately" and "in a
quarter minute" (and the reload wiped the add form while it was being filled in).

Now every element which shows a state registers at the entity hub of the panel and patches
itself when its entity reports. This test pins that machinery:

* `EntityHub` signals only the entities somebody listens to, only when they really changed,
  and stops when the listener unsubscribes
* the cards of pages/home.js carry their entity ids, so a signal finds them
* `_applyEntityState` relabels the toggle and fills the chip - including a chip which had no
  value at all before (the device reported for the first time)
* the page has no `refreshMs` anymore and gives its listeners back in `leave()`

Node is only used as a javascript engine; the test is skipped when node is not installed. The
page renders into the small dom of frontend_dom_stub.py - the frontend has no test runner and
no build step, so the markup it produced is parsed instead of a browser being started.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from tests.frontend_dom_stub import DOM_STUB

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND = os.path.join(REPO, 'custom_components', 'eltako', 'frontend')
NODE = shutil.which('node')

SCRIPT = DOM_STUB + r"""
// a static import cannot take a path from a variable - both are imported dynamically
const { EntityHub } = await import(`${process.argv[2]}/lib/entity_hub.js`);
const { page } = await import(`${process.argv[2]}/pages/home.js`);

/* ------------------------------------------------------------------ the hub */

const hubStates = { 'light.a': { state: 'off' }, 'light.b': { state: 'off' } };
const hub = new EntityHub(() => hubStates);
const signals = [];
const unsubscribe = hub.subscribe(['light.a'], (entityId, state) => signals.push([entityId, state.state]));

hub.update();                                        // nothing changed
hubStates['light.a'] = { state: 'on' };
hub.update();                                        // -> one signal
hub.update();                                        // same object again: no second signal
hubStates['light.b'] = { state: 'on' };
hub.update();                                        // not watched
unsubscribe();
hubStates['light.a'] = { state: 'off' };
hub.update();                                        // gone

/* ------------------------------------------------------- the page and its dom */

const device = (address, name, platform, entityIds, area) => ({
  gateway_id: 1, gateway_name: 'FAM14', gateway_set_up: True_, platform, source: 'ui',
  editable: True_, address, external_address: null, ha_device_id: null, name,
  eep: 'M5-38-08', area, sender: null, activity: null, sender_activity: null,
  entity_ids: entityIds, config: { id: address, name },
});

const ctx = {
  hass: { states: { 'light.ceiling_light': { state: 'off', attributes: { friendly_name: 'Ceiling light' } } } },
  state: {
    integrationInfo: { gateways: [{ id: 1, name: 'FAM14', connected: True_ }] },
    configuredDevices: [
      device('00-00-00-01', 'Ceiling light', 'light', ['light.ceiling_light'], 'Kitchen'),
      device('00-00-00-02', 'Thermometer', 'sensor', ['sensor.kitchen_temperature'], 'Kitchen'),
    ],
    statistics: { devices: [], unknown_devices: [], summary: {} },
    simpleFilter: '', simpleEditor: null, plugAndPlay: null, deviceForm: null,
  },
  api: { call: async () => null, lastError: null },
  root: null, requestRender() {}, requestContentRender() {},
};

const html = page.render(ctx);
const root = parseHtml(html);
ctx.root = root;                       // the panel hands the rendered dom to the page hooks

const chipOf = (entityId) => root.querySelector(`.state-chip[data-entity="${entityId}"]`);
const chipTextOf = (entityId) => {
  const chip = chipOf(entityId);
  return `${chip.querySelector('.chip-label').textContent.trim()}=${chip.querySelector('b').textContent.trim()}`;
};
// the chip is a button as well since pressing the state switches the device - this is the
// explicit on/off button next to it
const buttonOf = (entityId) => root.querySelectorAll(`button[data-entity="${entityId}"]`)
  .filter((button) => !button.classes.has('state-chip'))[0];
const cardOf = (address) => root.querySelector(`article[data-address="${address}"]`);

const before = {
  toggleLabel: buttonOf('light.ceiling_light').textContent.trim(),
  togglePrimary: buttonOf('light.ceiling_light').classList.contains('primary'),
  lightChipHidden: chipOf('light.ceiling_light').hidden,
  sensorChipHidden: chipOf('sensor.kitchen_temperature').hidden,
  sensorRowHidden: chipOf('sensor.kitchen_temperature').parentElement.hidden,
  statusLine: cardOf('00-00-00-02').querySelector('.device-status').textContent.trim(),
  silent: cardOf('00-00-00-02').classList.contains('silent'),
};

// the entities report: the light was switched on, the sensor sends its first value
page._applyEntityState(root, 'light.ceiling_light',
  { state: 'on', attributes: { friendly_name: 'Ceiling light' } });
page._applyEntityState(root, 'sensor.kitchen_temperature',
  { state: '21.5', attributes: { friendly_name: 'Thermometer Temperature', unit_of_measurement: '°C' } });

// a telegram of the thermometer arrived as well
page.onTelegram(ctx, { address: '00-00-00-02', local_address: null, known: True_ });

const after = {
  toggleLabel: buttonOf('light.ceiling_light').textContent.trim(),
  togglePrimary: buttonOf('light.ceiling_light').classList.contains('primary'),
  lightChip: chipTextOf('light.ceiling_light'),
  lightChipHidden: chipOf('light.ceiling_light').hidden,
  sensorChip: chipTextOf('sensor.kitchen_temperature'),
  sensorChipHidden: chipOf('sensor.kitchen_temperature').hidden,
  sensorRowHidden: chipOf('sensor.kitchen_temperature').parentElement.hidden,
  statusLine: cardOf('00-00-00-02').querySelector('.device-status').textContent.trim(),
  silent: cardOf('00-00-00-02').classList.contains('silent'),
  activity: ctx.state.configuredDevices[1].activity,
};

console.log(JSON.stringify({
  signals,
  refreshMs: page.refreshMs === undefined ? null : page.refreshMs,
  hasLeave: typeof page.leave === 'function',
  entityMarkers: [...html.matchAll(/data-entity="([^"]+)"/g)].map((match) => match[1]).sort(),
  before, after,
}, null, 1));
"""


@unittest.skipUnless(NODE, 'node is not installed')
class TestTheSimpleViewUpdatesItself(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # `true` cannot be written in a python string which is also valid javascript without
        # confusing the reader - the script uses True_ and it is defined here
        script = 'const True_ = true;\n' + SCRIPT
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'live.mjs')
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write(script)
            result = subprocess.run([NODE, path, FRONTEND], capture_output=True, text=True,
                                    timeout=120)
        if result.returncode != 0:
            raise AssertionError(f'node failed:\n{result.stderr}')
        cls.result = json.loads(result.stdout)

    def test_the_hub_signals_only_what_changed_and_only_while_subscribed(self):
        self.assertEqual([['light.a', 'on']], self.result['signals'])

    def test_the_page_has_no_reload_interval_anymore(self):
        self.assertIsNone(self.result['refreshMs'])

    def test_the_page_gives_its_listeners_back(self):
        self.assertTrue(self.result['hasLeave'])

    def test_every_element_which_shows_a_state_carries_its_entity(self):
        self.assertEqual(['light.ceiling_light', 'light.ceiling_light',
                          'sensor.kitchen_temperature'],
                         self.result['entityMarkers'])

    def test_the_toggle_follows_the_entity(self):
        before, after = self.result['before'], self.result['after']
        self.assertEqual('off', before['toggleLabel'])
        self.assertFalse(before['togglePrimary'])
        self.assertEqual('on', after['toggleLabel'])
        self.assertTrue(after['togglePrimary'])

    def test_the_chip_of_a_light_shows_the_new_state(self):
        self.assertFalse(self.result['before']['lightChipHidden'])
        self.assertEqual('state=on', self.result['after']['lightChip'])
        self.assertFalse(self.result['after']['lightChipHidden'])

    def test_the_first_value_of_a_device_makes_its_chip_appear(self):
        before, after = self.result['before'], self.result['after']
        self.assertTrue(before['sensorChipHidden'])
        self.assertTrue(before['sensorRowHidden'])
        self.assertFalse(after['sensorChipHidden'])
        self.assertFalse(after['sensorRowHidden'])
        self.assertEqual('Temperature=21.5 °C', after['sensorChip'])

    def test_a_telegram_updates_the_status_line_of_its_card(self):
        before, after = self.result['before'], self.result['after']
        self.assertEqual('never reported yet', before['statusLine'])
        self.assertTrue(before['silent'])
        self.assertEqual('last reported just now', after['statusLine'])
        self.assertFalse(after['silent'])
        self.assertEqual(0, after['activity']['silent_since_seconds'])


class TestTheStateSignalReachesThePanel(unittest.TestCase):
    """Both runtimes have to feed the hub - without that the cards never hear anything."""

    def test_home_assistant_state_updates_are_forwarded_to_the_hub(self):
        with open(os.path.join(FRONTEND, 'eltako-panel.js'), encoding='utf-8') as handle:
            source = handle.read()
        setter = re.search(r'set hass\(hass\) \{(.*?)\n  \}', source, re.DOTALL)
        self.assertIsNotNone(setter, 'eltako-panel.js has no hass setter')
        self.assertIn('this._entities.update()', setter.group(1))

    def test_the_standalone_shell_republishes_its_states(self):
        with open(os.path.join(REPO, 'eltako_standalone', 'shell', 'shell.js'),
                  encoding='utf-8') as handle:
            source = handle.read()
        # the state event updates hass.states in place, so the panel only notices it when
        # the property is assigned again
        self.assertIn('panel.hass = hass', source)
        subscribe = source[source.index('subscribeMessage'):]
        self.assertIn('publishStates()', subscribe[:subscribe.index('}, {')])


if __name__ == '__main__':
    unittest.main()
