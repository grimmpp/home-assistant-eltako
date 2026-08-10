"""The log of the integration, as the web ui reads it.

The 'Logs' page exists because the answers this integration produces are in the log and the
log is the hardest thing to reach: file access or the Home Assistant log viewer, mixed with
every other integration. So the records of the `eltako` logger are additionally kept in a ring
buffer (observation/integration_log.py).

What must not break: the buffer catches what is logged, it never lets a broken record kill the
thread which logged it, the filters of the page mean what they say, and the log level can be
changed at runtime - because that is the whole point of having it on the page.
"""
import logging
from unittest import TestCase

from custom_components.eltako.observation import integration_log
from custom_components.eltako.const import DATA_ELTAKO, DATA_INTEGRATION_LOG, DOMAIN

from tests.mocks import HassMock


class LogTestCase(TestCase):

    def setUp(self):
        self.hass = HassMock()
        self.hass.data = {}
        self.logger = logging.getLogger(DOMAIN)
        self._previous_level = self.logger.level
        self.handler = integration_log.async_setup_integration_log(self.hass, {})

    def tearDown(self):
        integration_log.async_unload_integration_log(self.hass)
        self.logger.setLevel(self._previous_level)


class TestTheBuffer(LogTestCase):

    def test_what_the_integration_logs_lands_in_the_buffer(self):
        self.logger.warning("[Gateway] [Id: 1] Serial port is not available")

        entries = integration_log.get_entries(self.hass)['entries']

        self.assertEqual(1, len(entries))
        self.assertEqual('WARNING', entries[0]['level'])
        self.assertIn('Serial port', entries[0]['message'])
        self.assertEqual(DOMAIN, entries[0]['logger'])

    def test_a_child_logger_is_caught_as_well(self):
        """'eltako.telegrams' is where the telegram log writes - it must be readable too."""
        logging.getLogger(f"{DOMAIN}.telegrams").warning("Received a telegram")

        entries = integration_log.get_entries(self.hass)['entries']

        self.assertEqual([f"{DOMAIN}.telegrams"], [entry['logger'] for entry in entries])

    def test_the_arguments_are_formatted(self):
        self.logger.warning("[Gateway] [Id: %s] busy with '%s'", 3, "bus scan")

        message = integration_log.get_entries(self.hass)['entries'][0]['message']

        self.assertEqual("[Gateway] [Id: 3] busy with 'bus scan'", message)

    def test_a_broken_format_string_does_not_raise(self):
        """A logging handler which throws takes the thread which logged with it - and that can
        be the serial thread of a gateway. The bug is shown instead of hidden."""
        # noqa: the broken call is the subject of this test - ruff finding it in real code is
        # exactly the point of having the rule switched on
        self.logger.warning("two placeholders %s %s", "only one argument")  # noqa: PLE1206

        entries = integration_log.get_entries(self.hass)['entries']

        self.assertEqual(1, len(entries))
        self.assertIn('cannot format', entries[0]['message'])

    def test_an_exception_keeps_its_traceback(self):
        try:
            raise ValueError("the port is gone")
        except ValueError:
            self.logger.error("[Gateway] cannot send", exc_info=True)

        entry = integration_log.get_entries(self.hass)['entries'][0]

        self.assertIn('ValueError', entry['exception'])
        self.assertIn('the port is gone', entry['exception'])

    def test_the_oldest_records_fall_out_and_are_counted(self):
        handler = integration_log.get_handler(self.hass)
        handler.records = type(handler.records)(maxlen=5)
        for number in range(12):
            self.logger.warning("record %d", number)

        result = integration_log.get_entries(self.hass)

        self.assertEqual(5, len(result['entries']))
        self.assertEqual("record 11", result['entries'][-1]['message'])
        # the page says so instead of pretending its oldest line is the beginning
        self.assertEqual(7, result['dropped'])

    def test_clearing_empties_the_buffer(self):
        self.logger.warning("something")
        integration_log.get_handler(self.hass).clear()

        self.assertEqual([], integration_log.get_entries(self.hass)['entries'])

    def test_setting_it_up_twice_does_not_duplicate_the_records(self):
        """async_setup runs again on every settings change - and a record stored twice would
        make the page unreadable."""
        integration_log.async_setup_integration_log(self.hass, {})
        self.logger.warning("only once")

        entries = integration_log.get_entries(self.hass)['entries']

        self.assertEqual(1, len(entries))

    def test_unloading_detaches_the_handler(self):
        integration_log.async_unload_integration_log(self.hass)
        self.logger.warning("after the unload")

        self.assertNotIn(self.handler, self.logger.handlers)
        self.assertNotIn(DATA_INTEGRATION_LOG, self.hass.data.get(DATA_ELTAKO, {}))


class TestTheFilters(LogTestCase):

    def setUp(self):
        super().setUp()
        self.logger.setLevel(logging.DEBUG)
        self.logger.debug("polling position 3")
        self.logger.info("[Gateway] [Id: 1] connected")
        self.logger.warning("[Bus Members] scan cancelled")
        self.logger.error("[Gateway] [Id: 1] serial port is gone")

    def test_a_level_filter_keeps_that_level_and_everything_worse(self):
        levels = [entry['level']
                  for entry in integration_log.get_entries(self.hass, level='warning')['entries']]

        self.assertEqual(['WARNING', 'ERROR'], levels)

    def test_the_search_looks_at_the_message(self):
        entries = integration_log.get_entries(self.hass, search='cancelled')['entries']

        self.assertEqual(1, len(entries))
        self.assertIn('cancelled', entries[0]['message'])

    def test_the_search_looks_at_the_logger_too(self):
        logging.getLogger(f"{DOMAIN}.telegrams").warning("a telegram")

        entries = integration_log.get_entries(self.hass, search='telegrams')['entries']

        self.assertEqual([f"{DOMAIN}.telegrams"], [entry['logger'] for entry in entries])

    def test_the_limit_keeps_the_newest_records(self):
        entries = integration_log.get_entries(self.hass, limit=2)['entries']

        self.assertEqual(2, len(entries))
        self.assertIn('serial port is gone', entries[-1]['message'])
        # ... and the total says how many there really are
        self.assertEqual(4, integration_log.get_entries(self.hass, limit=2)['total'])


class TestTheLogLevel(LogTestCase):

    def test_a_level_is_applied_to_the_logger(self):
        integration_log.apply_log_level(self.hass, 'debug')

        self.assertEqual(logging.DEBUG, self.logger.getEffectiveLevel())

    def test_inherit_gives_the_level_back_to_home_assistant(self):
        integration_log.apply_log_level(self.hass, 'debug')
        integration_log.apply_log_level(self.hass, integration_log.INHERIT)

        # NOTSET: the level of the parent logger counts again
        self.assertEqual(logging.NOTSET, self.logger.level)

    def test_debug_records_only_arrive_after_the_level_was_raised(self):
        """The reason the selector is on the page: with the default level the answer is simply
        not in the log, and finding out costs a restart otherwise."""
        integration_log.apply_log_level(self.hass, 'warning')
        self.logger.debug("not interesting yet")
        self.assertEqual([], integration_log.get_entries(self.hass)['entries'])

        integration_log.apply_log_level(self.hass, 'debug')
        self.logger.debug("now it matters")

        # the level change logs itself as well, which is exactly what one wants to see in a
        # log that suddenly gets louder - so it is the *debug* record which is checked here
        messages = [entry['message'] for entry in integration_log.get_entries(self.hass)['entries']]
        self.assertIn('now it matters', messages)
        self.assertNotIn('not interesting yet', messages)

    def test_the_page_is_told_which_level_is_in_effect(self):
        integration_log.apply_log_level(self.hass, 'info')

        described = integration_log.describe_level(self.hass)

        self.assertEqual('info', described['effective'])
        self.assertIn(integration_log.INHERIT, described['options'])

    def test_an_unknown_level_falls_back_to_inherit(self):
        self.assertIsNone(integration_log.level_number('nonsense'))
        self.assertIsNone(integration_log.level_number(''))
        self.assertEqual(logging.WARNING, integration_log.level_number('warning'))
