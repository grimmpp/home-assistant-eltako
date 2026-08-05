"""The feature list of the about page.

It is a hand written list in `frontend/pages/about.js` - the two things which silently rot are
the links into the docs folder (a renamed file leaves a 404 behind) and the names of the general
settings whose state is shown next to a feature (a renamed setting makes the state disappear
without any error). Both are pinned here.
"""
import os
import re
from unittest import TestCase

from custom_components.eltako import config_helpers

REPO = os.path.dirname(os.path.dirname(__file__))
ABOUT_JS = os.path.join(REPO, 'custom_components', 'eltako', 'frontend', 'pages', 'about.js')
DOCS_DIR = os.path.join(REPO, 'docs')


def read_about() -> str:
    with open(ABOUT_JS, encoding='utf-8') as handle:
        return handle.read()


def feature_section() -> str:
    """The FEATURE_GROUPS constant."""
    content = read_about()
    return content.split('const FEATURE_GROUPS = [', 1)[1].split('\n];', 1)[0]


class TestFeatureList(TestCase):

    def setUp(self):
        self.features = feature_section()

    def test_every_area_has_features(self):
        groups = re.findall(r'label:\s*"([^"]+)"', self.features)
        items = re.findall(r'\{\s*title:', self.features)

        self.assertGreaterEqual(len(groups), 5, groups)
        self.assertGreaterEqual(len(items), 25, len(items))

    def test_doc_links_point_to_existing_files(self):
        docs = re.findall(r'doc:\s*"([^"]+)"', self.features)

        self.assertGreater(len(docs), 5)
        for doc in docs:
            self.assertTrue(os.path.isfile(os.path.join(DOCS_DIR, doc)),
                            msg=f"docs/{doc} does not exist (linked from the about page)")

    def test_settings_of_features_exist(self):
        """A feature can show whether its setting is switched on - the name has to be real."""
        names = re.findall(r'setting:\s*"([^"]+)"', self.features)

        self.assertGreater(len(names), 2)
        known = set(config_helpers.DEFAULT_GENERAL_SETTINGS.keys())
        for name in names:
            self.assertIn(name, known, msg=f"'{name}' is not a general setting")

    def test_the_list_is_rendered_on_the_about_page(self):
        content = read_about()

        self.assertIn('<h2>Features</h2>', content)
        self.assertIn('_renderFeatures', content)
        # the page styles are appended by the panel - without them the cards have no layout
        self.assertRegex(content, r'styles:\s*[^\n]*ABOUT_STYLES')
        for rule in ('.features {', '.feature-card {', '.feature-list {', '.feature-intro {'):
            self.assertIn(rule, content, msg=rule)
