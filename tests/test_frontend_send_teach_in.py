"""The send form of the live view can also send the two teach-in telegrams.

Sending a value telegram by hand was possible, teaching in was not: a rocker switch which shall
be learned by an actuator, or the ELTAKO teach-in of a sender, had to be triggered somewhere else
(the teach-in button of a device, the simulation). The form offers both as its own input modes now
- only the profiles which really have such a telegram, and with the explanation of what is sent.

The descriptor comes from the real backend (`get_eep_descriptors` / `get_teach_in_descriptor`), so
a profile which loses its teach-in in python is noticed here. Node is only used as a javascript
engine; the test is skipped when node is not installed.
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
const { page } = await import(`${process.argv[2]}/pages/telegrams.js`);

const False_ = false, True_ = true;
globalThis.window = { eltakoStandalone: False_, dispatchEvent: () => {} };
globalThis.CustomEvent = class { constructor(type) { this.type = type; } };
globalThis.requestAnimationFrame = (callback) => setTimeout(callback, 0);

const descriptor = JSON.parse(process.argv[3]);

function makeContext() {
  return {
    hass: { states: {} },
    state: {
      telegrams: [], logInfo: { enabled: True_ }, statistics: null,
      integrationInfo: { gateways: [{ id: 1, name: 'FAM-USB' }] },
      telegramFilter: '', gatewayFilter: 'all', directionFilter: 'all', onlyUnknown: False_,
      paused: False_, unknownDetails: null,
      sendFormDescriptor: descriptor,
      sendForm: { gatewayId: 1, mode: 'eep', eep: 'A5-38-08', senderId: '00-00-B0-01',
                  fields: {}, raw: '', result: null, error: null },
    },
    api: {
      calls: [],
      lastError: null,
      async call(type, payload) {
        this.calls.push({ type, payload });
        return { sent: True_, mode: payload.mode, count: 2, telegram: 'a | b', hex: 'aa bb' };
      },
    },
    root: null,
    async loadRecentTelegrams() {},
    requestRender() {}, requestContentRender() {},
  };
}

function show(ctx) {
  const root = parseHtml(page.render(ctx));
  ctx.root = root;
  page.afterRender(ctx, root);
  return root;
}

const optionsOf = (root, id) => root.getElementById(id).querySelectorAll('option')
  .map((option) => option.getAttribute('value'));

/** Switch the form to a mode and render it again - what a user does with the dropdown. */
async function inMode(mode) {
  const ctx = makeContext();
  let root = show(ctx);
  await root.getElementById('send-mode').dispatch('change', mode);
  root = show(ctx);
  return { ctx, root };
}

const modes = optionsOf(show(makeContext()), 'send-mode');

/** The same in a mode, but with a descriptor the backend of an older version would answer. */
async function inModeWith(mode, changedDescriptor) {
  const ctx = makeContext();
  ctx.state.sendFormDescriptor = changedDescriptor;
  let root = show(ctx);
  await root.getElementById('send-mode').dispatch('change', mode);
  root = show(ctx);
  return root;
}

// a home assistant which was not restarted after the update answers without the teach-in block -
// the payload per profile is the same table, so the dropdown must not be empty because of it
const withoutTheBlock = await inModeWith('eltako_teach_in',
  { gateways: descriptor.gateways, eeps: descriptor.eeps });
// nothing at all about teach-in: then the form has to say why it offers nothing
const withoutAnything = await inModeWith('eltako_teach_in', {
  gateways: descriptor.gateways,
  eeps: descriptor.eeps.map(({ teach_in, eltako_teach_in, ...rest }) => rest),
});

const profile = await inMode('teach_in');
const eltako = await inMode('eltako_teach_in');

// sending in both modes: only the profile and the address it is sent from go over the wire
await profile.root.getElementById('send-submit').click();
await eltako.root.getElementById('send-submit').click();
const sentProfile = profile.ctx.api.calls.find((call) => call.type === 'eltako/send_telegram');
const sentEltako = eltako.ctx.api.calls.find((call) => call.type === 'eltako/send_telegram');

// a value telegram still carries its fields
const valueCtx = makeContext();
await show(valueCtx).getElementById('send-submit').click();

console.log(JSON.stringify({
  modes,
  profileEeps: optionsOf(profile.root, 'send-eep'),
  eltakoEeps: optionsOf(eltako.root, 'send-eep'),
  // the profile of the value mode has no ELTAKO teach-in, so the mode change had to move on
  eltakoEepAfterSwitch: eltako.ctx.state.sendForm.eep,
  profileEepAfterSwitch: profile.ctx.state.sendForm.eep,
  profileFields: profile.root.querySelectorAll('.send-field').length,
  profileHelp: profile.root.querySelectorAll('#send-form .field-help')
    .map((help) => help.textContent.replace(/\s+/g, ' ').trim()),
  eltakoHelp: eltako.root.querySelectorAll('#send-form .field-help')
    .map((help) => help.textContent.replace(/\s+/g, ' ').trim()),
  sentProfile, sentEltako,
  eepsWithoutTheBlock: optionsOf(withoutTheBlock, 'send-eep'),
  eepsWithoutAnything: optionsOf(withoutAnything, 'send-eep'),
  noteWithoutAnything: withoutAnything.querySelectorAll('#send-form .field-help')
    .map((help) => help.textContent.replace(/\s+/g, ' ').trim()).join(' '),
  sentValues: valueCtx.api.calls.find((call) => call.type === 'eltako/send_telegram'),
  // what the notice says after a teach-in which was two telegrams
  notice: show(Object.assign(profile.ctx, {})).querySelector('#send-form .notice')
    .textContent.replace(/\s+/g, ' ').trim(),
}, null, 1));
"""


@unittest.skipUnless(NODE, 'node is not installed')
class TestTheTeachInModesOfTheSendForm(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from custom_components.eltako.core.websocket import (get_eep_descriptors,
                                                             get_teach_in_descriptor)

        descriptor = json.dumps({
            'gateways': [{'id': 1, 'name': 'FAM-USB', 'base_id': 'FF-AA-80-00'}],
            'eeps': get_eep_descriptors(),
            'teach_in': get_teach_in_descriptor(),
        })
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'teach_in.mjs')
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write(SCRIPT)
            result = subprocess.run([NODE, path, FRONTEND, descriptor],
                                    capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise AssertionError(f'node failed:\n{result.stderr}')
        cls.result = json.loads(result.stdout)

    def test_both_teach_ins_are_offered_next_to_the_value_telegram(self):
        self.assertEqual(['eep', 'teach_in', 'eltako_teach_in', 'raw'], self.result['modes'])

    def test_both_modes_offer_the_sender_profiles_of_the_teach_in_table(self):
        """`EEP_WITH_TEACH_IN_BUTTONS` is the list - those are the profiles taught in at all."""
        from custom_components.eltako.catalog.teach_in import teach_in_button_eep_names

        self.assertEqual(teach_in_button_eep_names(), sorted(self.result['eltakoEeps']))
        self.assertEqual(teach_in_button_eep_names(), sorted(self.result['profileEeps']))
        # a sensor profile of the library is not among them, however well it could announce itself
        self.assertNotIn('A5-04-02', self.result['profileEeps'])

    def test_the_chosen_profile_survives_the_mode_change_if_it_can(self):
        self.assertEqual('A5-38-08', self.result['profileEepAfterSwitch'])
        self.assertEqual('A5-38-08', self.result['eltakoEepAfterSwitch'])

    def test_a_teach_in_has_no_value_fields(self):
        self.assertEqual(0, self.result['profileFields'])

    def test_the_form_says_what_it_will_send(self):
        profile = ' '.join(self.result['profileHelp'])
        eltako = ' '.join(self.result['eltakoHelp'])

        self.assertIn('announce', profile)
        self.assertIn('function, type and manufacturer', profile)
        self.assertIn('memory', eltako)
        self.assertIn('e0400d80', eltako)       # the data bytes of A5-38-08

    def test_sending_carries_the_mode_the_profile_and_the_address(self):
        self.assertEqual({'gateway_id': 1, 'mode': 'teach_in', 'eep': 'A5-38-08',
                          'sender_id': '00-00-B0-01'}, self.result['sentProfile']['payload'])
        self.assertEqual({'gateway_id': 1, 'mode': 'eltako_teach_in', 'eep': 'A5-38-08',
                          'sender_id': '00-00-B0-01'}, self.result['sentEltako']['payload'])

    def test_a_value_telegram_still_carries_its_fields(self):
        payload = self.result['sentValues']['payload']
        self.assertEqual('eep', payload['mode'])
        self.assertIn('switching_command', payload['fields'])

    def test_an_older_backend_does_not_leave_the_dropdown_empty(self):
        """Without `teach_in.eltako_eeps` the payload per profile is the same table."""
        from custom_components.eltako.catalog.teach_in import teach_in_button_eep_names

        self.assertEqual(teach_in_button_eep_names(),
                         sorted(self.result['eepsWithoutTheBlock']))

    def test_a_descriptor_which_knows_no_teach_in_says_why_it_offers_nothing(self):
        """An empty dropdown without a word is the bug this feature had - not silence."""
        self.assertEqual([], self.result['eepsWithoutAnything'])
        self.assertIn('restart Home Assistant', self.result['noteWithoutAnything'])

    def test_the_notice_says_how_many_telegrams_were_sent(self):
        """An RPS teach-in is a press and its release - two telegrams, not one."""
        self.assertIn('Sent 2 telegrams', self.result['notice'])


if __name__ == '__main__':
    unittest.main()
