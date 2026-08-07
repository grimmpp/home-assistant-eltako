"""The generated parts of the documentation must match the code.

`generate_docs.py` renders the list of supported devices and EEPs out of the code. That only
helps as long as nobody forgets to run it - so this test renders them again and compares. A
device added to the catalog or an EEP added to a platform schema therefore fails here until
the documentation was regenerated.
"""

import os
import sys
import unittest

REPOSITORY_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPOSITORY_ROOT not in sys.path:
    sys.path.insert(0, REPOSITORY_ROOT)

import generate_docs
from custom_components.eltako.catalog import help_catalog


REGENERATE = 'Regenerate it with "python generate_docs.py".'


class TestGeneratedDocs(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.catalog = help_catalog.build_catalog(generate_docs.DOC_BASE_URL)

    def _read(self, path):
        with open(path, encoding='utf-8') as handle:
            return handle.read()

    def test_supported_devices_page_is_up_to_date(self):
        self.assertEqual(
            generate_docs.render_supported_devices_page(self.catalog),
            self._read(generate_docs.SUPPORTED_DEVICES_DOC),
            msg=f'docs/supported-devices.md does not match the code. {REGENERATE}')

    def test_readme_section_is_up_to_date(self):
        readme = self._read(generate_docs.README)
        self.assertIn(generate_docs.README_MARKER_START, readme,
                      msg='The generated block of README.md lost its start marker.')
        self.assertIn(generate_docs.README_MARKER_END, readme,
                      msg='The generated block of README.md lost its end marker.')
        self.assertEqual(generate_docs.render_readme(self.catalog, readme), readme,
                         msg=f'The supported devices section of README.md is stale. {REGENERATE}')

    def test_nothing_is_out_of_date(self):
        """The check mode of the generator - the same thing a maintainer would run."""
        self.assertEqual([], generate_docs.generate(check=True),
                         msg=f'Generated documentation is out of date. {REGENERATE}')

    def test_every_device_of_the_catalog_is_documented(self):
        """The point of generating: no device can be missing from the readme."""
        readme = self._read(generate_docs.README)
        for device in self.catalog['devices']:
            if device['is_gateway']:
                continue                  # gateways are described in their own section
            self.assertIn(device['hw_type'], readme,
                          msg=f"Device {device['hw_type']} of the catalog is missing in README.md. {REGENERATE}")

    def test_every_eep_is_documented(self):
        readme = self._read(generate_docs.README)
        for eep in self.catalog['eeps']:
            self.assertIn(eep['eep'], readme,
                          msg=f"EEP {eep['eep']} is missing in README.md. {REGENERATE}")


if __name__ == '__main__':
    unittest.main()
