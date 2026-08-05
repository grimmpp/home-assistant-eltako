"""Links between the documents of this repository must be relative and must resolve.

Relative and not `https://github.com/grimmpp/home-assistant-eltako/tree/main/...`: an absolute
link always points at the state of `main`, so a document added on a branch is a 404 until it is
merged, and a fork links back into this repository instead of into itself. A relative link
follows whatever branch, fork or checkout it is read in - on github, in a pull request and in
an editor alike.

The exceptions are the places where a relative link cannot work and are listed below: github
features (issues, pull requests, commits) have no file behind them, and the help page of the
web ui renders inside Home Assistant, where a relative link would point into the Home Assistant
frontend - `help_catalog.py` builds those from `REPOSITORY_URL` on purpose.
"""

import os
import re
import unittest
from unittest import TestCase

REPOSITORY_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPOSITORY_URL = 'https://github.com/grimmpp/home-assistant-eltako'

# folders which are not documentation of this repository
SKIPPED_DIRS = {'.git', '.venv', 'node_modules', '__pycache__', '.pytest_cache', 'blueprints'}

# A link into this repository addresses a **file** when it goes through tree/, blob/ or raw/ -
# those are the ones which have to be relative. Everything else of the repository url (issues,
# pull requests, commits, releases, uploaded assets) is a github feature with no file behind it
# and can only be absolute.
FILE_LINK = re.compile(re.escape(REPOSITORY_URL) + r'/(?:tree|blob|raw)/')

# [text](target) - the target ends at the first closing bracket or whitespace, which is enough
# for the links used here (no titles, no nested parentheses in a path)
LINK = re.compile(r'\[[^\]]*\]\(([^)\s]+)\)')


def markdown_files() -> list[str]:
    files = []
    for root, dirs, names in os.walk(REPOSITORY_ROOT):
        dirs[:] = [d for d in dirs if d not in SKIPPED_DIRS]
        files.extend(os.path.join(root, name) for name in names if name.lower().endswith('.md'))
    return sorted(files)


def links_of(path: str) -> list[str]:
    with open(path, encoding='utf-8') as handle:
        return LINK.findall(handle.read())


def relative_to_root(path: str) -> str:
    return os.path.relpath(path, REPOSITORY_ROOT).replace(os.sep, '/')


class TestLinksIntoTheRepositoryAreRelative(TestCase):

    def test_no_document_links_to_a_file_through_github(self):
        offenders = []

        for path in markdown_files():
            for target in links_of(path):
                if FILE_LINK.match(target):
                    offenders.append(f"{relative_to_root(path)} -> {target}")

        self.assertEqual([], offenders,
                         "link to a file of this repository through github.com. Use a path "
                         "relative to the document instead, it survives branches and forks:\n  "
                         + "\n  ".join(offenders))

    def test_the_check_recognises_a_file_link(self):
        self.assertTrue(FILE_LINK.match(f'{REPOSITORY_URL}/tree/main/docs/readme.md'))
        self.assertTrue(FILE_LINK.match(f'{REPOSITORY_URL}/blob/main/ha.yaml'))
        self.assertIsNone(FILE_LINK.match(f'{REPOSITORY_URL}/issues'))
        self.assertIsNone(FILE_LINK.match(f'{REPOSITORY_URL}/pull/141'))

    def test_the_readme_links_its_documentation_relatively(self):
        """The readme is the entry point - it carries most of the links."""
        targets = links_of(os.path.join(REPOSITORY_ROOT, 'README.md'))
        docs = [target for target in targets if 'docs/' in target and not target.startswith('http')]

        self.assertTrue(docs, msg='the readme stopped linking the documentation')
        for target in docs:
            self.assertFalse(target.startswith('/'),
                             msg=f"'{target}' is relative to the server root, not to the readme - "
                                 f"github resolves it to github.com/{target.lstrip('/')}")


class TestRelativeLinksResolve(TestCase):

    def test_every_relative_link_points_at_something(self):
        offenders = []

        for path in markdown_files():
            directory = os.path.dirname(path)
            for target in links_of(path):
                if re.match(r'^[a-z][a-z0-9+.-]*:', target) or target.startswith('#'):
                    continue                       # url or an anchor inside the document
                target = target.split('#', 1)[0]   # strip the anchor of a section link
                if not target:
                    continue
                if not os.path.exists(os.path.join(directory, target)):
                    offenders.append(f"{relative_to_root(path)} -> {target}")

        self.assertEqual([], offenders,
                         "relative link which does not resolve:\n  " + "\n  ".join(offenders))

    def test_the_check_would_notice_a_dead_link(self):
        """Guard against the regex silently matching nothing."""
        self.assertEqual(['docs/nowhere.md'], LINK.findall('see [the docs](docs/nowhere.md).'))
        self.assertFalse(os.path.exists(os.path.join(REPOSITORY_ROOT, 'docs/nowhere.md')))


if __name__ == '__main__':
    unittest.main()
