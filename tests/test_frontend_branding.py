"""Branding of the web ui: the Eltako logo in the header and the colour palette.

These are static checks on the shipped css/js. They cannot judge whether it *looks* good, but
they do catch the mistakes which silently undo the branding: a hardcoded grey creeping back in,
the logo drifting out of the white bar, or an accent that stops following the theme.

The layout itself was measured with a real layout engine (headless Chrome) while it was built: at
340, 600, 900 and 1400 px the logo's centre matched the centre of the white bar exactly, it kept
16 px (10 px on a phone) to the right edge, and neither the title nor the navigation ran into it.
What can regress afterwards is the css that produces it, so that is what is pinned here.
"""

import os
import re
from unittest import TestCase

FRONTEND = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                        'custom_components', 'eltako', 'frontend')


def read(*parts):
    with open(os.path.join(FRONTEND, *parts), encoding='utf-8') as handle:
        return handle.read()


class TestHeaderLogo(TestCase):
    """The logo sits at the right of the white bar, vertically centred over its whole height.

    The white bar is the header *and* the navigation below it - they share the card background.
    That is why the logo is a child of .topbar and not of the header: inside the header it could
    only be centred over the title row, which puts it in the upper half of the white area.
    """

    def setUp(self):
        self.styles = read('lib', 'styles.js')
        self.panel = read('eltako-panel.js')

    def test_it_is_centred_over_the_whole_bar(self):
        logo = self._rule('.topbar .brand-logo')

        self.assertIn('position: absolute', logo)
        self.assertIn('top: 50%', logo)
        self.assertIn('translateY(-50%)', logo)
        # ...against the bar, not against the page
        self.assertIn('position: relative', self._rule('.topbar'))

    def test_it_is_flush_right(self):
        self.assertRegex(self._rule('.topbar .brand-logo'), r'right:\s*\d+px')

    def test_the_logo_lives_next_to_header_and_nav(self):
        """As a child of the header it could only be centred over the title row."""
        topbar = self.panel.split('<div class="topbar">', 1)[1].split('</div>', 1)[0]

        for part in ('<header class="app-head">', '<nav id="nav">', 'class="brand-logo"'):
            self.assertIn(part, topbar, msg=part)

        header = self.panel.split('<header class="app-head">', 1)[1].split('</header>', 1)[0]
        self.assertNotIn('brand-logo', header)

    def test_header_and_nav_reserve_room_for_it(self):
        """Otherwise a long title or a wide navigation runs underneath the logo."""
        for selector in ('header.app-head', 'nav'):
            padding = re.search(r'padding: \d+px (\d+)px', self._rule(selector))
            self.assertIsNotNone(padding, msg=f'{selector} has no padding shorthand')
            reserved = int(padding.group(1))
            height = int(re.search(r'height: (\d+)px', self._rule('.topbar .brand-logo')).group(1))
            self.assertGreater(reserved, height, msg=f'{selector} reserves too little room')

    def test_title_and_logo_are_separate_items(self):
        """Menu button, icon, title and version travel together on the left."""
        self.assertIn('<span class="brand">', self.panel)
        brand = self.panel.split('<span class="brand">', 1)[1].split('</span>\n', 1)[0] \
            + self.panel.split('<span class="brand">', 1)[1].split('</header>', 1)[0]
        for part in ('menu-button-slot', 'brand-title', 'brand-version'):
            self.assertIn(part, brand, msg=f'{part} belongs next to the title')

    def test_the_logo_is_large_enough_to_read(self):
        """Both logo files are square, so the height is the whole size."""
        height = int(re.search(r'height:\s*(\d+)px', self._rule('.topbar .brand-logo')).group(1))

        self.assertGreaterEqual(height, 48)
        # it must still fit into the bar
        min_height = int(re.search(r'min-height:\s*(\d+)px', self._rule('header.app-head')).group(1))
        self.assertLessEqual(height, min_height - 8)

    def test_the_title_gives_way_on_a_narrow_screen(self):
        """The logo keeps its place at the right edge; the title truncates instead of wrapping."""
        self.assertIn('text-overflow: ellipsis', self.styles)
        self.assertIn('white-space: nowrap', self._rule('header.app-head .brand-title'))

    def test_both_logo_files_exist(self):
        for name in ('eltako-logo.svg', 'eltako-logo.png'):
            self.assertTrue(os.path.isfile(os.path.join(FRONTEND, 'img', name)), msg=name)

    def _rule(self, selector):
        """Body of a css rule of the panel stylesheet."""
        match = re.search(re.escape(selector) + r'\s*\{([^}]*)\}', self.styles)
        self.assertIsNotNone(match, msg=f'rule {selector} is gone')
        return match.group(1)


class TestTheName(TestCase):
    """The web ui carries one name, and it is written down in two places.

    The heading is markup in the panel, the sidebar entry is PANEL_TITLE in const.py - so
    renaming one of them alone gives an installation whose sidebar and heading disagree.
    """

    NAME = 'ELTAKO EnOcean Tool'

    def test_the_heading_is_the_name(self):
        heading = re.search(r'<span class="brand-title">([^<]*)</span>', read('eltako-panel.js'))

        self.assertIsNotNone(heading, msg='the brand title is gone')
        self.assertEqual(self.NAME, heading.group(1).strip())

    def test_the_sidebar_entry_is_the_same_name(self):
        constants = os.path.join(os.path.dirname(FRONTEND), 'const.py')
        with open(constants, encoding='utf-8') as handle:
            title = re.search(r'PANEL_TITLE: Final = "([^"]*)"', handle.read())

        self.assertIsNotNone(title, msg='PANEL_TITLE is gone')
        self.assertEqual(self.NAME, title.group(1))

    def test_the_standalone_browser_tab_says_it_too(self):
        shell = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                             'eltako_standalone', 'shell', 'index.html')
        with open(shell, encoding='utf-8') as handle:
            title = re.search(r'<title>([^<]*)</title>', handle.read())

        self.assertIsNotNone(title, msg='the shell page has no title')
        self.assertEqual(self.NAME, title.group(1).strip())


class TestColourPalette(TestCase):
    """Light and blue like eltako.com - not grey with orange accents."""

    ELTAKO_BLUE = '#0064AF'

    def setUp(self):
        self.styles = read('lib', 'styles.js')

    def test_brand_blue_is_the_one_of_the_logo(self):
        self.assertIn(f'--eltako-blue: {self.ELTAKO_BLUE}', self.styles)

    def test_the_accent_lightens_on_a_dark_theme(self):
        """#0064AF on a dark background is too dark to read."""
        self.assertIn('--eltako-blue-light', self.styles)
        dark = self.styles.split('prefers-color-scheme: dark', 1)[1]
        self.assertIn('--eltako-accent: var(--eltako-blue-light)', dark)

    def test_neutral_surfaces_carry_a_blue_wash(self):
        for token in ('--eltako-tint:', '--eltako-tint-strong:', '--eltako-hover:'):
            line = self._token(token)
            self.assertIn('color-mix', line, msg=token)
            self.assertIn('var(--eltako-blue)', line, msg=token)

    def test_the_wash_is_mixed_into_the_theme_colour(self):
        """Not a hardcoded light surface - a user's dark theme must survive it."""
        self.assertIn('var(--divider-color', self._token('--eltako-border:'))
        background = re.search(r'\n\s*background: (color-mix[^;]*);', self.styles).group(1)
        self.assertIn('var(--primary-background-color', background)
        self.assertIn('var(--eltako-blue)', background)

    def test_no_plain_grey_is_left(self):
        """rgba(127,127,127,...) as a *fill* was what made the ui look grey.

        It stays allowed as the fallback of a theme variable inside the border token, where
        the blue is mixed on top of it anyway.
        """
        offenders = [line.strip() for line in self.styles.splitlines()
                     if 'rgba(127,127,127' in line and '--eltako-border:' not in line]

        self.assertEqual([], offenders)

    def test_the_amber_is_reserved_for_warnings(self):
        """It used to colour the navigation counters too, which is what read as "orange"."""
        badge = re.search(r'nav a \.badge \{([^}]*)\}', self.styles).group(1)

        self.assertIn('var(--eltako-accent)', badge)
        self.assertNotIn('yellow', badge)
        self.assertNotIn('f9a825', badge.lower())

    def test_warnings_go_through_one_token(self):
        """So the warning colour can be changed in one place instead of seven."""
        users = [line.strip() for line in self.styles.splitlines()
                 if 'label-badge-yellow' in line and '--eltako-warn:' not in line]

        self.assertEqual([], users)
        self.assertIn('--eltako-warn:', self.styles)

    def test_the_unknown_device_rows_are_not_an_orange_block(self):
        """A whole table in an amber wash was the largest orange area of the ui.

        The single 'unknown' tag inside the row still carries the warning colour.
        """
        row = re.search(r'\.unknown-row \{([^}]*)\}', self.styles).group(1)

        self.assertIn('--eltako-tint', row)
        self.assertNotIn('warn', row)
        self.assertIn('var(--eltako-warn)', re.search(r'\.tag\.unknown \{([^}]*)\}', self.styles).group(1))

    def test_no_second_hardcoded_blue(self):
        """The group and relation rows used to carry their own #005ca9."""
        self.assertNotIn('005ca9', self.styles.lower())

    def test_pages_use_the_tokens_too(self):
        """Page local styles must not reintroduce their own greys."""
        pages = os.path.join(FRONTEND, 'pages')
        offenders = []
        for name in sorted(os.listdir(pages)):
            if not name.endswith('.js'):
                continue
            for number, line in enumerate(read('pages', name).splitlines(), 1):
                if 'rgba(127,127,127' in line:
                    offenders.append(f'{name}:{number}')

        self.assertEqual([], offenders)

    def _token(self, name):
        return next(line for line in self.styles.splitlines() if name in line)
