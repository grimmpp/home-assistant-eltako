"""The Grafana dashboards ship with the integration and are pushed via its HTTP API.

The dashboards are versioned together with the data model they query (tags/fields of
timeseries.py), so a new tag cannot end up without a panel. Two ways into Grafana, both from
the same files: file provisioning (dev container) and the api (button in the web ui).
"""
import json
import os
import unittest
from unittest import TestCase, mock

from custom_components.eltako import grafana_sync
from custom_components.eltako.const import CONF_GRAFANA_TOKEN, CONF_GRAFANA_URL
from custom_components.eltako.timeseries import FIELD_KEYS, TAG_KEYS


class TestShippedDashboards(TestCase):

    def test_dashboards_are_shipped_with_the_integration(self):
        dashboards = grafana_sync.load_dashboards()

        self.assertGreaterEqual(len(dashboards), 5)
        titles = [dashboard['title'] for dashboard in dashboards]
        for expected in ('Eltako - Telegram overview', 'Eltako - Telegrams per device',
                         'Eltako - Errors and bus health', 'Eltako - Product and test inspector'):
            self.assertIn(expected, titles)

    def test_every_dashboard_is_valid_and_complete(self):
        for dashboard in grafana_sync.load_dashboards():
            name = dashboard['_file']
            self.assertTrue(dashboard.get('uid'), msg=name)
            self.assertTrue(dashboard.get('title'), msg=name)
            self.assertIn('eltako', dashboard.get('tags', []), msg=name)
            self.assertTrue(dashboard.get('panels'), msg=name)
            for panel in dashboard['panels']:
                self.assertTrue(panel.get('title'), msg=name)
                self.assertEqual(panel.get('datasource', {}).get('uid'),
                                 grafana_sync.DATASOURCE_UID, msg=f"{name}/{panel.get('title')}")
                for target in panel.get('targets', []):
                    self.assertEqual(target.get('queryType'), 'flux',
                                     msg=f"{name}/{panel['title']}")
                    self.assertIn('${measurement}', target.get('query', ''),
                                  msg=f"{name}/{panel['title']}")

    def test_uids_are_unique(self):
        uids = [dashboard['uid'] for dashboard in grafana_sync.load_dashboards()]

        self.assertEqual(len(uids), len(set(uids)))

    @staticmethod
    def _decoded_field_names() -> set[str]:
        """Every property an EEP of the library can decode.

        Those become influx fields dynamically (`record['decoded']`), so a panel may query
        them - but only if they really exist. A typo like 'temperatur' is caught here.
        """
        import inspect

        from eltakobus import eep as eep_module

        names = set()
        for _name, cls in inspect.getmembers(eep_module, inspect.isclass):
            for attribute in dir(cls):
                if attribute.startswith('_'):
                    continue
                if isinstance(getattr(cls, attribute, None), property):
                    names.add(attribute)
        return names

    def test_panels_only_query_fields_which_can_exist(self):
        """A panel querying a field nobody writes would stay empty forever."""
        import re

        exported = ({tag for tag, _key in TAG_KEYS} | set(FIELD_KEYS)
                    | {'count', 'platform'}                 # always written / derived
                    | self._decoded_field_names())
        variables = {'$value', '${value}'}                  # chosen by the user at runtime

        for dashboard in grafana_sync.load_dashboards():
            for panel in dashboard['panels']:
                for target in panel.get('targets', []):
                    for field in re.findall(r'r\._field == "([^"]+)"', target['query']):
                        if field in variables:
                            continue
                        self.assertIn(field, exported,
                                      msg=f"{dashboard['_file']}/{panel['title']}: field "
                                          f"'{field}' is neither exported by timeseries.py nor "
                                          f"a decodable EEP value")

    def test_panels_only_filter_on_tags_which_are_exported(self):
        """Same for tags: `r.foo == "x"` on a tag which is never written filters everything out."""
        import re

        exported = {tag for tag, _key in TAG_KEYS} | {'platform'}
        # flux built-ins and the pivoted columns of the raw telegram table
        ignored = {'_measurement', '_field', '_value', '_time', '_start', '_stop'}

        for dashboard in grafana_sync.load_dashboards():
            for panel in dashboard['panels']:
                for target in panel.get('targets', []):
                    for tag in re.findall(r'r\.([a-z_][a-z0-9_]*) ==', target['query']):
                        if tag in ignored:
                            continue
                        self.assertIn(tag, exported,
                                      msg=f"{dashboard['_file']}/{panel['title']}: tag "
                                          f"'{tag}' is not exported by timeseries.py")

    def test_decode_error_dashboard_uses_the_exported_tag(self):
        """The error dashboard needs the decode_error tag - added for exactly this purpose."""
        self.assertIn('decode_error', [tag for tag, _key in TAG_KEYS])

        errors = next(d for d in grafana_sync.load_dashboards()
                      if d['uid'] == 'eltako-errors')
        queries = " ".join(target['query'] for panel in errors['panels']
                           for target in panel.get('targets', []))
        self.assertIn('decode_error', queries)

    def test_describe_dashboards_for_the_web_ui(self):
        described = grafana_sync.describe_dashboards()

        self.assertTrue(described)
        for entry in described:
            self.assertTrue(entry['title'])
            self.assertGreater(entry['panels'], 0)


class TestAuthHeader(TestCase):

    def test_service_account_token_is_a_bearer(self):
        header = grafana_sync._auth_header('glsa_abc123')

        self.assertEqual(header['Authorization'], 'Bearer glsa_abc123')

    def test_user_password_becomes_basic_auth(self):
        header = grafana_sync._auth_header('admin:admin')

        self.assertTrue(header['Authorization'].startswith('Basic '))

    def test_no_token_no_header(self):
        self.assertEqual(grafana_sync._auth_header(''), {})
        self.assertEqual(grafana_sync._auth_header(None), {})


class TestRetargetDatasource(TestCase):
    """The dashboards are re-pointed at the datasource which actually exists."""

    def test_every_reference_is_replaced(self):
        dashboard = {
            'panels': [{'datasource': {'type': 'influxdb', 'uid': 'eltako-influxdb'},
                        'targets': [{'datasource': {'type': 'influxdb', 'uid': 'eltako-influxdb'}}]}],
            'templating': {'list': [{'datasource': {'type': 'influxdb', 'uid': 'eltako-influxdb'}}]},
        }

        grafana_sync._retarget(dashboard, 'my-influx')

        self.assertEqual(dashboard['panels'][0]['datasource']['uid'], 'my-influx')
        self.assertEqual(dashboard['panels'][0]['targets'][0]['datasource']['uid'], 'my-influx')
        self.assertEqual(dashboard['templating']['list'][0]['datasource']['uid'], 'my-influx')


class TestSync(TestCase):
    """The sync reports what happened instead of raising."""

    def _settings(self, url='http://grafana.local:3000', token='glsa_x'):
        return {CONF_GRAFANA_URL: url, CONF_GRAFANA_TOKEN: token}

    def test_without_a_url_it_explains_itself(self):
        result = grafana_sync.sync(self._settings(url=''))

        self.assertFalse(result['success'])
        self.assertIn('URL', result['error'])
        self.assertEqual(result['dashboards'], [])

    def test_unreachable_grafana_is_reported(self):
        with mock.patch.object(grafana_sync, '_request', return_value=(500, {'message': 'boom'})):
            result = grafana_sync.sync(self._settings())

        self.assertFalse(result['success'])
        self.assertIn('did not answer', result['error'])

    def test_missing_influx_datasource_is_reported(self):
        def fake(url, token, method='GET', payload=None):
            if url.endswith('/api/health'):
                return 200, {'version': '11.0.0'}
            if url.endswith('/api/datasources'):
                return 200, []          # no datasource at all
            return 200, {}

        with mock.patch.object(grafana_sync, '_request', side_effect=fake):
            result = grafana_sync.sync(self._settings())

        self.assertFalse(result['success'])
        self.assertIn('datasource', result['error'])

    def test_successful_sync_reports_every_dashboard(self):
        posted = []

        def fake(url, token, method='GET', payload=None):
            if url.endswith('/api/health'):
                return 200, {'version': '11.0.0'}
            if url.endswith('/api/datasources'):
                return 200, [{'uid': 'other-influx', 'type': 'influxdb'}]
            if url.endswith('/api/folders') and method == 'GET':
                return 200, []
            if url.endswith('/api/folders') and method == 'POST':
                return 200, {'uid': 'folder-1'}
            if url.endswith('/api/dashboards/db'):
                posted.append(payload)
                return 200, {'url': '/d/x/y'}
            return 200, {}

        with mock.patch.object(grafana_sync, '_request', side_effect=fake):
            result = grafana_sync.sync(self._settings())

        self.assertTrue(result['success'], msg=result.get('error'))
        self.assertEqual(len(result['dashboards']), len(grafana_sync.load_dashboards()))
        self.assertTrue(all(entry['success'] for entry in result['dashboards']))

        for payload in posted:
            self.assertTrue(payload['overwrite'])
            self.assertEqual(payload['folderUid'], 'folder-1')
            # the datasource of the target grafana was substituted
            self.assertNotIn('"eltako-influxdb"', json.dumps(payload))
            self.assertNotIn('id', payload['dashboard'])

    def test_a_failing_dashboard_does_not_stop_the_others(self):
        calls = {'n': 0}

        def fake(url, token, method='GET', payload=None):
            if url.endswith('/api/health'):
                return 200, {'version': '11.0.0'}
            if url.endswith('/api/datasources'):
                return 200, [{'uid': 'eltako-influxdb', 'type': 'influxdb'}]
            if url.endswith('/api/folders'):
                return 200, [{'title': 'Eltako', 'uid': 'folder-1'}]
            if url.endswith('/api/dashboards/db'):
                calls['n'] += 1
                if calls['n'] == 1:
                    return 403, {'message': 'permission denied'}
                return 200, {'url': '/d/x/y'}
            return 200, {}

        with mock.patch.object(grafana_sync, '_request', side_effect=fake):
            result = grafana_sync.sync(self._settings())

        self.assertFalse(result['success'])
        self.assertEqual(len([e for e in result['dashboards'] if not e['success']]), 1)
        self.assertIn('permission denied', result['dashboards'][0]['message'])
        # all of them were attempted
        self.assertEqual(calls['n'], len(grafana_sync.load_dashboards()))


class TestProvisioningUsesTheSameFiles(TestCase):
    """The dev container must mount the dashboards of the integration, not a copy."""

    def test_compose_mounts_the_integration_dashboards(self):
        import yaml

        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'dev', 'docker-compose.yml')
        with open(path, encoding='utf-8') as handle:
            compose = yaml.safe_load(handle)

        volumes = compose['services']['grafana']['volumes']
        self.assertTrue(any('custom_components/eltako/grafana/dashboards' in volume
                            for volume in volumes),
                        msg="the dev container must use the dashboards of the integration")


if __name__ == '__main__':
    unittest.main()


class TestPanelQueriesAreValidFlux(TestCase):
    """Execute every panel query against a reachable InfluxDB.

    The static checks above only verify names. They cannot catch an invalid query - e.g.
    `count()` on a column which is part of the group key, which InfluxDB rejects with
    "cannot aggregate columns that are part of the group key". That panel showed an error in
    Grafana instead of data. Running the queries is the only way to find that.

    Skipped when no InfluxDB is reachable, so the suite stays runnable without one:
        cd dev && ./start-analytics.sh
    """

    URL = os.environ.get('ELTAKO_TEST_INFLUX_URL', 'http://localhost:8086')
    TOKEN = os.environ.get('ELTAKO_TEST_INFLUX_TOKEN', 'eltako-dev-token')
    ORG = os.environ.get('ELTAKO_TEST_INFLUX_ORG', 'home')
    BUCKET = os.environ.get('ELTAKO_TEST_INFLUX_BUCKET', 'eltako')

    # Grafana replaces these before sending the query. The substitutes have to keep the query
    # valid: a multi-value variable becomes a json array, a textbox a plain string.
    SUBSTITUTIONS = {
        '${bucket}': BUCKET,
        '${measurement}': 'eltako_telegram',
        '${device:json}': '["$__all"]',
        '${address:json}': '["$__all"]',
        '${eep:json}': '["$__all"]',
        '$search': '',
        '$payload': '',
        '$value': 'temperature',
        '${value}': 'temperature',
        'v.timeRangeStart': '-1h',
        'v.timeRangeStop': 'now()',
        'v.windowPeriod': '1m',
    }

    @classmethod
    def setUpClass(cls):
        import urllib.error
        import urllib.request

        try:
            with urllib.request.urlopen(f"{cls.URL}/health", timeout=3) as response:
                if response.status != 200:
                    raise unittest.SkipTest(f"InfluxDB at {cls.URL} is not healthy")
        except (urllib.error.URLError, OSError) as e:
            raise unittest.SkipTest(f"No InfluxDB at {cls.URL} ({e}) - "
                                    f"start it with 'cd dev && ./start-analytics.sh'")

    def _resolve(self, query: str) -> str:
        for placeholder, value in self.SUBSTITUTIONS.items():
            query = query.replace(placeholder, value)
        return query

    def _run(self, query: str) -> tuple[int, str]:
        import urllib.error
        import urllib.request

        request = urllib.request.Request(
            f"{self.URL}/api/v2/query?org={self.ORG}", data=query.encode(),
            headers={'Authorization': f'Token {self.TOKEN}',
                     'Content-Type': 'application/vnd.flux',
                     'Accept': 'application/csv'}, method='POST')
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return response.status, response.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode(errors='replace')

    def test_every_panel_query_is_accepted_by_influxdb(self):
        failures = []
        checked = 0
        for dashboard in grafana_sync.load_dashboards():
            for panel in dashboard['panels']:
                for target in panel.get('targets', []):
                    checked += 1
                    status, body = self._run(self._resolve(target['query']))
                    # a query without matching data is fine - only a rejected query is not
                    if status != 200 or '"code":"invalid"' in body:
                        failures.append(f"{dashboard['_file']}/{panel['title']}: "
                                        f"{body.strip()[:200]}")

        self.assertGreater(checked, 20, msg="no panel queries were checked")
        self.assertEqual(failures, [], msg="InfluxDB rejected panel queries:\n  "
                                           + "\n  ".join(failures))
