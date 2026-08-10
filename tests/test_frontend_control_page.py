"""The 'Control' page: what you switch has to stand above what you press once.

A teach-in button carries the same name as its device ("FSR14_4x ch1"), and the backend
delivers the entities sorted by entity id - so the first row of that name used to be the
button with its single "Press", while the light with On/Off stood fourteen rows further down.
That reads like the device cannot be switched at all. This test renders the real page with a
realistic entity list and pins the order and the controls.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND = os.path.join(REPO, 'custom_components', 'eltako', 'frontend')
CONTROL_PAGE = os.path.join(FRONTEND, 'pages', 'control.js')
NODE = shutil.which('node')

# a static import cannot take a path from a variable - the page is imported dynamically
SCRIPT = """
import { readFileSync } from 'node:fs';
const { page } = await import(process.argv[2]);
const fixture = JSON.parse(readFileSync(process.argv[3], 'utf8'));
const ctx = {
  state: {
    controlEntities: fixture.entities,
    configuredDevices: fixture.devices,
    telegramForm: fixture.form,
    // both send forms opened, so the fields themselves are part of the html
    controlSendOpen: { 'light.eltako_gw_0_00_00_00_05': true,
                       'sensor.eltako_ff_aa_dd_81': true },
    controlSendValues: {},
    controlShowSensors: true,
  },
  api: { call: async () => null, lastError: null },
  root: null, requestRender() {}, requestContentRender() {},
};
const html = page.render(ctx);
const rows = [...html.matchAll(/data-entity="([^"]+)"/g)].map((match) => match[1]);
const controlsOf = (id) => {
  const at = html.indexOf(`data-entity="${id}"`);
  return at < 0 ? '' : html.slice(at, html.indexOf('</tr>', at));
};
const sendFormOf = (id) => {
  const at = html.indexOf(`data-send-row="${id}"`);
  return at < 0 ? '' : html.slice(at, html.indexOf('</tr>', at));
};
// which entity would get a send form at all, and with which profile
const telegrams = {};
for (const entity of fixture.entities) {
  const telegram = page._telegramOf(ctx, entity, page._deviceOf(ctx, entity));
  telegrams[entity.entity_id] = telegram
    ? { eep: telegram.eep, address: telegram.address, role: telegram.role,
        fields: telegram.descriptor.fields } : null;
}
// the same form again, but with the dimming command chosen: a profile which writes different
// bytes depending on one field must offer different fields as well
ctx.state.controlSendValues = { 'light.eltako_gw_0_00_00_00_05': { command: '2' } };
const dimmingHtml = page.render(ctx);
const dimmingAt = dimmingHtml.indexOf('data-send-row="light.eltako_gw_0_00_00_00_05"');
const dimmingForm = dimmingAt < 0 ? ''
  : dimmingHtml.slice(dimmingAt, dimmingHtml.indexOf('</tr>', dimmingAt));
ctx.state.controlSendValues = {};

// the same page with the teach-in button entities switched on
ctx.state.controlShowTeachInButtons = true;
const withButtons = page.render(ctx);
const rowsWithButtons = [...withButtons.matchAll(/data-entity="([^"]+)"/g)].map((m) => m[1]);
ctx.state.controlShowTeachInButtons = false;

// the type bar of the toolbar: one button per kind of entity, and what it filters
const toolbar = page.renderToolbar(ctx);
const counts = page._typeCounts(ctx);
ctx.state.controlTypes = { light: false };
const rowsWithoutLights = [...page.render(ctx).matchAll(/data-entity="([^"]+)"/g)].map((m) => m[1]);
ctx.state.controlTypes = { teach_in: true };
const rowsWithTeachInType = [...page.render(ctx).matchAll(/data-entity="([^"]+)"/g)].map((m) => m[1]);
delete ctx.state.controlTypes;

console.log(JSON.stringify({
  rows, rowsWithButtons, telegrams, dimmingForm,
  toolbar, counts, rowsWithoutLights, rowsWithTeachInType,
  teachIn: [...html.matchAll(/data-teach-in="([^"]+)"/g)].map((match) => match[1]),
  teachInHtml: (() => {
    const at = html.indexOf('data-teach-in="light.eltako_gw_0_00_00_00_01"');
    return at < 0 ? '' : html.slice(Math.max(0, at - 200), at + 200);
  })(),
  light: controlsOf('light.eltako_gw_0_00_00_00_01'),
  dimmer: controlsOf('light.eltako_gw_0_00_00_00_05'),
  dimmerForm: sendFormOf('light.eltako_gw_0_00_00_00_05'),
  sensorForm: sendFormOf('sensor.eltako_ff_aa_dd_81'),
  html,
}));
"""


def entities() -> list[dict]:
    """The entities of a FAM14 with an FSR14 channel, a FUD14 and their teach-in buttons."""
    def entity(entity_id, platform, name, state, attributes=None, eep=None):
        return {'entity_id': entity_id, 'platform': platform, 'name': name, 'state': state,
                'attributes': attributes or {}, 'area': None, 'eep': eep,
                'actions': [], 'gateway_id': 0, 'gateway_name': 'FAM Test'}

    return [
        # the backend delivers them sorted by (platform, entity_id): buttons come first
        entity('button.eltako_gw_0_00_00_00_01_teach_in_button', 'button', 'FSR14_4x ch1',
               'unknown', eep='M5-38-08'),
        entity('button.eltako_gw_0_00_00_00_05_teach_in_button', 'button', 'FUD14', 'unknown',
               eep='A5-38-08'),
        entity('climate.eltako_gw_0_00_00_00_08', 'climate', 'FAE14SSR ch1', 'off',
               {'temperature': 21.0, 'hvac_modes': ['off', 'heat']}, 'A5-10-06'),
        entity('light.eltako_gw_0_00_00_00_01', 'light', 'FSR14_4x ch1', 'on',
               {'supported_color_modes': ['onoff'], 'color_mode': 'onoff'}, 'M5-38-08'),
        entity('light.eltako_gw_0_00_00_00_05', 'light', 'FUD14', 'off',
               {'supported_color_modes': ['brightness']}, 'A5-38-08'),
        entity('sensor.eltako_gw_0_00_00_00_01_power', 'sensor', 'FSR14_4x ch1 power', '12.5',
               {'unit_of_measurement': 'W'}, 'M5-38-08'),
        entity('sensor.eltako_ff_aa_dd_81', 'sensor', 'Temperature sensor', '21.0',
               {'unit_of_measurement': '°C'}, 'A5-04-02'),
    ]


def devices() -> list[dict]:
    """The same devices as the configuration delivers them (eltako/devices/list)."""
    return [
        {'gateway_id': 0, 'platform': 'light', 'address': '00-00-00-01', 'eep': 'M5-38-08',
         'name': 'FSR14_4x ch1', 'sender': {'id': '00-00-B0-01', 'eep': 'A5-38-08'},
         'sender_taught_in': False,      # the memory was read, the sender is not in it
         'entity_ids': ['light.eltako_gw_0_00_00_00_01']},
        {'gateway_id': 0, 'platform': 'light', 'address': '00-00-00-05', 'eep': 'A5-38-08',
         'name': 'FUD14', 'sender': {'id': '00-00-B0-05', 'eep': 'A5-38-08'},
         'sender_taught_in': True,
         'entity_ids': ['light.eltako_gw_0_00_00_00_05']},
        {'gateway_id': 0, 'platform': 'climate', 'address': '00-00-00-08', 'eep': 'A5-10-06',
         'name': 'FAE14SSR ch1', 'sender': {'id': '00-00-B0-08', 'eep': 'A5-10-06'},
         'sender_taught_in': None,       # nothing is known about this memory
         'entity_ids': ['climate.eltako_gw_0_00_00_00_08']},
        # a sensor has no sender: what can be sent is its own telegram
        {'gateway_id': 0, 'platform': 'sensor', 'address': 'FF-AA-DD-81', 'eep': 'A5-04-02',
         'name': 'Temperature sensor', 'sender': None,
         'entity_ids': ['sensor.eltako_ff_aa_dd_81']},
    ]


def send_form() -> dict:
    """The real descriptors of the backend - fields and start values per EEP."""
    from custom_components.eltako.core.websocket import get_eep_descriptors

    return {'gateways': [], 'eeps': get_eep_descriptors()}


@unittest.skipUnless(NODE, 'node is not installed - the page cannot be rendered here')
class TestControlPageOrder(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        script = os.path.join(cls.tmp.name, 'render.mjs')
        data = os.path.join(cls.tmp.name, 'entities.json')
        with open(script, 'w', encoding='utf-8') as handle:
            handle.write(SCRIPT)
        with open(data, 'w', encoding='utf-8') as handle:
            json.dump({'entities': entities(), 'devices': devices(), 'form': send_form()}, handle)

        process = subprocess.run([NODE, script, CONTROL_PAGE, data],
                                 capture_output=True, text=True, timeout=120, cwd=REPO)
        assert process.returncode == 0, f"node failed:\n{process.stderr[-2000:]}"
        cls.result = json.loads(process.stdout)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_the_teach_in_button_entities_are_left_out(self):
        """Their action sits in the row of the device - twice would be twice as confusing."""
        rows = self.result['rows']

        self.assertNotIn('button.eltako_gw_0_00_00_00_01_teach_in_button', rows)
        self.assertNotIn('button.eltako_gw_0_00_00_00_05_teach_in_button', rows)

    def test_the_devices_stand_above_the_buttons(self):
        """With the teach-in buttons shown, they belong below what can be operated."""
        rows = self.result['rowsWithButtons']

        self.assertLess(rows.index('light.eltako_gw_0_00_00_00_01'),
                        rows.index('button.eltako_gw_0_00_00_00_01_teach_in_button'),
                        msg=f"the light must come before its teach-in button: {rows}")
        self.assertLess(rows.index('climate.eltako_gw_0_00_00_00_08'),
                        rows.index('button.eltako_gw_0_00_00_00_05_teach_in_button'))

    def test_a_relay_can_be_switched(self):
        self.assertIn('data-action="turn_on"', self.result['light'])
        self.assertIn('data-action="turn_off"', self.result['light'])

    def test_a_dimmer_has_a_brightness_slider(self):
        self.assertIn('data-field="brightness"', self.result['dimmer'])
        self.assertIn('type="range"', self.result['dimmer'])

    def test_every_row_says_what_it_is(self):
        """Two rows of the same name are only distinguishable by their kind."""
        self.assertIn('>Light<', self.result['html'])
        self.assertIn('>Heating/cooling<', self.result['html'])

    def test_an_actuator_sends_with_the_profile_of_its_sender(self):
        """A relay does not listen to its own address - the telegram is the one of its sender."""
        telegram = self.result['telegrams']['light.eltako_gw_0_00_00_00_05']

        self.assertEqual(telegram['eep'], 'A5-38-08')
        self.assertEqual(telegram['address'], '00-00-B0-05')
        self.assertEqual(telegram['role'], 'sender')

    def test_a_sensor_sends_its_own_telegram(self):
        telegram = self.result['telegrams']['sensor.eltako_ff_aa_dd_81']

        self.assertEqual(telegram['eep'], 'A5-04-02')
        self.assertEqual(telegram['address'], 'FF-AA-DD-81')
        self.assertEqual(telegram['role'], 'device')

    def test_every_configured_device_has_input_fields(self):
        """The point of the whole thing: no configured device without a way to send to it."""
        for entity_id in ('light.eltako_gw_0_00_00_00_01', 'light.eltako_gw_0_00_00_00_05',
                          'climate.eltako_gw_0_00_00_00_08', 'sensor.eltako_ff_aa_dd_81'):
            telegram = self.result['telegrams'][entity_id]
            self.assertIsNotNone(telegram, msg=f"{entity_id} offers no telegram to send")
            self.assertTrue(telegram['fields'], msg=f"{entity_id} has no fields")

    def test_the_fields_of_the_profile_are_rendered_with_their_start_values(self):
        form = self.result['dimmerForm']

        # A5-38-08 starts as the switching command, so these are its values
        for field in ('command', 'switching_command', 'time', 'lock', 'learn_button'):
            self.assertIn(f'data-field="{field}"', form)
        self.assertIn('data-send="light.eltako_gw_0_00_00_00_05"', form)

    def test_a_choice_is_a_dropdown_with_names_instead_of_a_number(self):
        form = self.result['dimmerForm']

        self.assertIn('>switch</option>', form)
        self.assertIn('>dim</option>', form)
        self.assertIn('>on</option>', form)          # switching_command
        self.assertIn('>data telegram</option>', form)   # learn_button

    def test_a_number_carries_its_unit_and_its_range(self):
        form = self.result['dimmerForm']

        self.assertIn('<span class="unit">s</span>', form)
        self.assertIn('type="number"', form)
        self.assertIn('max="6553.5"', form)

    def test_only_the_fields_which_are_really_read_are_offered(self):
        """A5-38-08 writes different bytes for switching and for dimming."""
        switching = self.result['dimmerForm']
        dimming = self.result['dimmingForm']

        self.assertNotIn('data-field="dimming_value"', switching)
        self.assertIn('data-field="lock"', switching)

        for field in ('dimming_value', 'ramping_time', 'dimming_range', 'store_final_value'):
            self.assertIn(f'data-field="{field}"', dimming)
        self.assertNotIn('data-field="lock"', dimming)

    def test_the_sensor_form_carries_its_measured_values(self):
        form = self.result['sensorForm']

        self.assertIn('data-field="temperature"', form)
        self.assertIn('data-field="humidity"', form)
        self.assertIn('value="21"', form)

    def test_an_entity_without_a_configured_device_has_no_send_form(self):
        """The diagnostic entities of a gateway are no devices - there is nothing to send."""
        self.assertIsNone(self.result['telegrams']['sensor.eltako_gw_0_00_00_00_01_power'])

    def test_an_actuator_whose_sender_is_missing_can_be_taught_in(self):
        """The FSR14 channel of the fixture has sender_taught_in=False."""
        self.assertIn('light.eltako_gw_0_00_00_00_01', self.result['teachIn'])
        self.assertIn('teach in (missing)', self.result['teachInHtml'])

    def test_a_taught_in_device_needs_no_button(self):
        self.assertNotIn('light.eltako_gw_0_00_00_00_05', self.result['teachIn'])

    def test_a_device_whose_memory_is_unknown_is_offered_the_teach_in_too(self):
        """A wireless actuator answers no question about its memory - the button stays."""
        self.assertIn('climate.eltako_gw_0_00_00_00_08', self.result['teachIn'])

    def test_a_sensor_is_never_taught_in(self):
        self.assertNotIn('sensor.eltako_ff_aa_dd_81', self.result['teachIn'])

    def test_sensors_stay_hidden_until_they_are_asked_for(self):
        rows = self.result['rows']

        # this run has "show sensors" ticked, so they are there - the filter is what hides them
        self.assertIn('sensor.eltako_ff_aa_dd_81', rows)


@unittest.skipUnless(NODE, 'node is not installed - the page cannot be rendered here')
class TestTypeBar(unittest.TestCase):
    """The toolbar: one button per kind of entity instead of two checkboxes."""

    @classmethod
    def setUpClass(cls):
        # the same render run as above - node is started once, no matter in which order
        # (or alone) these classes are executed
        if getattr(TestControlPageOrder, 'result', None) is None:
            TestControlPageOrder.setUpClass()
        cls.result = TestControlPageOrder.result

    def test_every_kind_has_a_button(self):
        toolbar = self.result['toolbar']

        for key in ('light', 'switch', 'cover', 'climate', 'select', 'button',
                    'binary_sensor', 'sensor', 'teach_in'):
            self.assertIn(f'data-type="{key}"', toolbar, msg=f"no button for {key}")
        self.assertIn('data-type-all', toolbar)
        self.assertIn('data-type-reset', toolbar)

    def test_a_button_says_how_many_rows_it_stands_for(self):
        counts = self.result['counts']

        self.assertEqual(2, counts['light'])          # FSR14 channel and FUD14
        self.assertEqual(1, counts['climate'])
        self.assertEqual(2, counts['sensor'])
        # the teach-in buttons are counted as their own kind, not as buttons
        self.assertEqual(2, counts['teach_in'])
        self.assertEqual(0, counts['button'])

    def _button(self, key: str) -> str:
        """The whole <button> of one kind - its classes stand in front of its data-type."""
        toolbar = self.result['toolbar']
        at = toolbar.index(f'data-type="{key}"')
        return toolbar[toolbar.rindex('<button', 0, at):toolbar.index('</button>', at)]

    def test_a_kind_which_no_entity_has_is_left_out(self):
        """Otherwise the bar shows every kind the integration knows, not this installation."""
        self.assertIn('is-empty', self._button('cover'),
                      msg="the empty 'covers' button must be hidden")
        self.assertNotIn('is-empty', self._button('light'))

    def test_a_kind_which_is_shown_is_marked_as_pressed(self):
        light = self._button('light')
        sensor = self._button('sensor')

        self.assertIn('aria-pressed="true"', light)
        # this run has "show sensors" ticked - the old switch decides the start value
        self.assertIn('aria-pressed="true"', sensor)

    def test_switching_a_kind_off_removes_its_rows(self):
        rows = self.result['rowsWithoutLights']

        self.assertNotIn('light.eltako_gw_0_00_00_00_01', rows)
        self.assertNotIn('light.eltako_gw_0_00_00_00_05', rows)
        self.assertIn('climate.eltako_gw_0_00_00_00_08', rows)

    def test_the_teach_in_button_has_its_own_switch(self):
        rows = self.result['rowsWithTeachInType']

        self.assertIn('button.eltako_gw_0_00_00_00_01_teach_in_button', rows)
        self.assertIn('light.eltako_gw_0_00_00_00_01', rows)


# load() with the *real* initial state of the panel. It is what decides whether the buttons are
# there after a reload - and `configuredDevices: []` in that state is truthy, which is exactly
# how they once disappeared: a "load it if it is missing" never fired.
LOAD_SCRIPT = """
import { readFileSync } from 'node:fs';
const [pagePath, dataPath, frontendDir] = process.argv.slice(2);
const { page } = await import(pagePath);
const fixture = JSON.parse(readFileSync(dataPath, 'utf8'));

function initialStateOfThePanel() {
  const source = readFileSync(`${frontendDir}/eltako-panel.js`, 'utf-8');
  const start = source.indexOf('this.state = {');
  let depth = 0, end = -1;
  for (let index = source.indexOf('{', start); index < source.length; index += 1) {
    if (source[index] === '{') depth += 1;
    else if (source[index] === '}') { depth -= 1; if (depth === 0) { end = index; break; } }
  }
  return new Function(`return ${source.slice(source.indexOf('{', start), end + 1)};`)();
}

const calls = [];
const answers = {
  'eltako/entities/list': { entities: fixture.entities },
  'eltako/devices/list': { devices: fixture.devices },
  'eltako/send_telegram_form': fixture.form,
};
const ctx = {
  state: initialStateOfThePanel(),
  api: {
    call: async (command) => { calls.push(command); return answers[command] ?? null; },
    lastError: null,
    hass: { connection: { subscribeMessage: async () => () => {} } },
  },
  root: null, requestRender() {}, requestContentRender() {},
};

await page.load(ctx);
const html = page.render(ctx);
console.log(JSON.stringify({
  calls,
  deviceCount: (ctx.state.configuredDevices || []).length,
  hasSendButton: html.includes('data-send-toggle='),
  hasTeachInButton: html.includes('data-teach-in='),
}));
"""


@unittest.skipUnless(NODE, 'node is not installed - the page cannot be rendered here')
class TestControlPageAfterAReload(unittest.TestCase):
    """Everything the buttons need has to be loaded by load() - nothing may be assumed."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        script = os.path.join(cls.tmp.name, 'load.mjs')
        data = os.path.join(cls.tmp.name, 'fixture.json')
        with open(script, 'w', encoding='utf-8') as handle:
            handle.write(LOAD_SCRIPT)
        with open(data, 'w', encoding='utf-8') as handle:
            json.dump({'entities': entities(), 'devices': devices(), 'form': send_form()}, handle)

        process = subprocess.run([NODE, script, CONTROL_PAGE, data, FRONTEND],
                                 capture_output=True, text=True, timeout=120, cwd=REPO)
        assert process.returncode == 0, f"node failed:\n{process.stderr[-2000:]}"
        cls.result = json.loads(process.stdout)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_the_configuration_is_read(self):
        self.assertIn('eltako/devices/list', self.result['calls'])
        self.assertEqual(len(devices()), self.result['deviceCount'],
                         msg="without the devices there is no telegram and no teach-in")

    def test_the_profiles_are_read(self):
        self.assertIn('eltako/send_telegram_form', self.result['calls'])

    def test_the_buttons_are_there_right_after_loading(self):
        self.assertTrue(self.result['hasSendButton'], "no 'telegram...' button after a reload")
        self.assertTrue(self.result['hasTeachInButton'], "no 'teach in' button after a reload")


if __name__ == '__main__':
    unittest.main()
