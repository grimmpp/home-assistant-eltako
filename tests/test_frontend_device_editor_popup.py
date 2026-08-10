"""The add / edit form of the devices page is a popup.

The form is opened from all over that page: the **+ Add device** button of the toolbar, an
unconfigured bus channel deep inside a bus section, an address which only sent telegrams, and
the details popup of a device. As a block above the table it opened where nobody was looking,
and editing a row far down the list meant scrolling up to the form and back again afterwards
to see what became of the row.

So it is the same popup the rest of the web ui uses (frontend/lib/details.js `renderModal`):
it opens in front of the page, the page behind it keeps its scroll position and its tables,
and it closes the three ways every popup here closes - the ×, Cancel, a click next to it.
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
const { page } = await import(`${process.argv[2]}/pages/devices_config.js`);

const True_ = true, False_ = false;
globalThis.confirm = () => True_;
globalThis.alert = () => {};
globalThis.setTimeout = globalThis.setTimeout;

const deviceForm = {
  gateways: [{ id: 1, name: 'FAM14', base_id: 'FF-AA-80-00' }],
  platforms: [
    { platform: 'light', label: 'Light', help: 'A switching or dimming actuator',
      device_types: [{ value: 'FSR14_4x', label: 'FSR14-4x', eep: 'M5-38-08',
                       sender_eep: 'A5-38-08', hw_type: 'FSR14-4x' }],
      fields: [{ name: 'id', label: 'Address', type: 'address', required: True_ },
               { name: 'name', label: 'Name', type: 'text' },
               { name: 'eep', label: 'EEP', type: 'text' }] },
    { platform: 'binary_sensor', label: 'Binary sensor', fields: [
      { name: 'id', label: 'Address', type: 'address', required: True_ }] },
  ],
};

const device = {
  gateway_id: 1, gateway_name: 'FAM14', platform: 'light', source: 'ui', editable: True_,
  address: '00-00-00-05', external_address: null, name: 'Kitchen light', eep: 'M5-38-08',
  area: 'Kitchen', sender: { id: '00-00-B0-05', eep: 'A5-38-08' }, activity: null,
  sender_activity: null, entity_ids: [], config: { id: '00-00-00-05', name: 'Kitchen light' },
  simulated: False_, ha_device_id: null,
};

const calls = [];
function makeContext(state = {}) {
  return {
    hass: { states: {} },
    state: {
      configuredDevices: [device], deviceForm,
      integrationInfo: { gateways: [{ id: 1, name: 'FAM14', connected: True_, type: 'fam14',
                                      base_id: 'FF-AA-80-00' }] },
      statistics: { devices: [], unknown_devices: [] },
      busMembers: null, configFilter: '', configSort: 'address', deviceView: 'flat',
      editor: null, memoryPanel: null, deviceDetails: null, ...state,
    },
    api: { call: async (type, payload) => { calls.push([type, payload]); return { ok: True_ }; },
           lastError: null },
    root: null,
    navigate() {},
    loadIntegrationInfo: async () => {}, loadStatistics: async () => {},
    requestRender() {}, requestContentRender() {},
  };
}

function show(ctx) {
  const html = page.render(ctx);
  const root = parseHtml(html);
  ctx.root = root;
  page.afterRender(ctx, root);
  return { root, html };
}

/* ------------------------------------------- the toolbar opens it as a popup */

const ctx = makeContext();
const toolbar = parseHtml(page.renderToolbar(ctx));
ctx.root = toolbar;
page.bindToolbar(ctx, toolbar);
await toolbar.getElementById('add-device').click();
const openedByToolbar = !!ctx.state.editor && ctx.state.editor.mode;

const addCtx = makeContext({ editor: { mode: 'add', platform: 'light', gatewayId: 1,
                                       values: {}, error: null } });
const add = show(addCtx);
const overlay = add.root.querySelector('aside.modal-overlay[data-editor-backdrop]');
const card = add.root.querySelector('#device-editor');

/* ------------------------------------------------ editing a row prefills it */

const rowCtx = makeContext();
const rowRoot = show(rowCtx).root;
await rowRoot.querySelector('button[data-edit]').click();
const editorAfterEdit = rowCtx.state.editor;

/* ------------------------------------------------------ the ways out of it */

async function closeWith(press) {
  const closeCtx = makeContext({ editor: { mode: 'add', platform: 'light', gatewayId: 1,
                                           values: { id: 'FF-AA-80-01' }, error: null } });
  const closeRoot = show(closeCtx).root;
  await press(closeRoot);
  return closeCtx.state.editor;
}
const afterCancel = await closeWith((root) => root.getElementById('editor-cancel').click());
const afterCross = await closeWith((root) => root.getElementById('editor-close').click());
const afterBackdrop = await closeWith((root) =>
  root.querySelector('[data-editor-backdrop]').click());
// a click *inside* the card must not close it - that is where the form is
const afterInsideClick = await closeWith((root) => root.querySelector('#device-editor').click());

/* ----------------------------------------------------------- saving still works */

const saveCtx = makeContext({ editor: { mode: 'add', platform: 'light', gatewayId: 1,
                                        values: {}, error: null } });
const saveRoot = show(saveCtx).root;
// the stub only knows the values a test types in - every input needs one
const typed = { id: 'FF-AA-80-01', name: 'New light', eep: 'A5-38-08' };
for (const [field, value] of Object.entries(typed)) {
  saveRoot.querySelector(`[data-field="${field}"]`).value = value;
}
await saveRoot.getElementById('editor-save').click();

console.log(JSON.stringify({
  openedByToolbar,
  // the popup markup: an overlay the panel can lift out of the page, with a card inside
  isOverlay: !!overlay,
  cardIsInsideOverlay: !!card && !!card.closest('aside.modal-overlay'),
  cardClasses: card ? [...card.classes] : [],
  cardTitle: add.root.querySelector('#device-editor .modal-head h3').textContent.trim(),
  // and the whole form is inside it, not left behind on the page
  fieldsInsidePopup: !!add.root.querySelector('#device-editor #device-fields'),
  buttonsInsidePopup: ['editor-save', 'editor-cancel', 'editor-close']
    .filter((id) => !!add.root.querySelector(`#device-editor [id="${id}"]`)),
  addressFieldInsidePopup: !!add.root.querySelector('#device-editor [data-field="id"]'),
  // the page behind it is unchanged - the table is still there
  tableStillRendered: add.root.querySelectorAll('table tbody tr[data-address]').length,
  editorAfterEdit: editorAfterEdit && { mode: editorAfterEdit.mode, values: editorAfterEdit.values },
  detailsClosedByEdit: rowCtx.state.deviceDetails,
  afterCancel, afterCross, afterBackdrop,
  insideClickKeepsItOpen: !!afterInsideClick,
  saved: calls.filter(([, payload]) => payload && payload.device)
    .map(([type, payload]) => [type, payload.device]),
  editorAfterSave: saveCtx.state.editor,
}, null, 1));
"""


@unittest.skipUnless(NODE, 'node is not installed')
class TestTheDeviceFormIsAPopup(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'editor_popup.mjs')
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write(SCRIPT)
            result = subprocess.run([NODE, path, FRONTEND], capture_output=True, text=True,
                                    timeout=120)
        if result.returncode != 0:
            raise AssertionError(f'node failed:\n{result.stderr}')
        cls.result = json.loads(result.stdout)

    def test_add_device_opens_the_form(self):
        self.assertEqual('add', self.result['openedByToolbar'])

    def test_the_form_is_rendered_as_a_popup(self):
        """An `aside.modal-overlay` - that is what the panel lifts out of the scrolling page."""
        self.assertTrue(self.result['isOverlay'])
        self.assertTrue(self.result['cardIsInsideOverlay'])
        self.assertIn('modal-card', self.result['cardClasses'])
        self.assertIn('modal-wide', self.result['cardClasses'])   # a form needs two columns

    def test_the_popup_says_what_it_does(self):
        self.assertEqual('Add device', self.result['cardTitle'])

    def test_the_whole_form_lives_inside_the_popup(self):
        self.assertTrue(self.result['fieldsInsidePopup'])
        self.assertTrue(self.result['addressFieldInsidePopup'])
        self.assertEqual(['editor-save', 'editor-cancel', 'editor-close'],
                         self.result['buttonsInsidePopup'])

    def test_the_page_behind_it_keeps_its_table(self):
        self.assertEqual(1, self.result['tableStillRendered'])

    def test_edit_on_a_row_opens_it_with_that_device(self):
        editor = self.result['editorAfterEdit']
        self.assertEqual('edit', editor['mode'])
        self.assertEqual('00-00-00-05', editor['values']['id'])
        self.assertIsNone(self.result['detailsClosedByEdit'])   # only one popup at a time

    def test_the_three_ways_out_all_close_it(self):
        self.assertIsNone(self.result['afterCancel'])
        self.assertIsNone(self.result['afterCross'])
        self.assertIsNone(self.result['afterBackdrop'])

    def test_a_click_in_the_form_does_not_close_it(self):
        self.assertTrue(self.result['insideClickKeepsItOpen'])

    def test_saving_from_the_popup_creates_the_device(self):
        self.assertEqual(
            [['eltako/devices/add',
              {'id': 'FF-AA-80-01', 'name': 'New light', 'eep': 'A5-38-08'}]],
            self.result['saved'])
        self.assertIsNone(self.result['editorAfterSave'])


class TestItUsesTheSharedPopup(unittest.TestCase):
    """One popup renderer for the whole web ui - the page must not build a second one."""

    def _source(self, *parts):
        with open(os.path.join(FRONTEND, *parts), encoding='utf-8') as handle:
            return handle.read()

    def test_the_page_asks_the_shared_module_for_the_popup(self):
        source = self._source('pages', 'devices_config.js')
        self.assertIn('renderModal', source)
        self.assertNotIn('class="modal-overlay"', source)

    def test_the_details_popup_is_built_from_the_same_shell(self):
        details = self._source('lib', 'details.js')
        self.assertIn('return renderModal(', details)

    def test_the_panel_lifts_every_popup_out_of_the_scrolling_page(self):
        """position:fixed alone does not work - see the comment in eltako-panel.js."""
        self.assertIn('aside.detail-drawer, aside.modal-overlay',
                      self._source('eltako-panel.js'))


if __name__ == '__main__':
    unittest.main()
