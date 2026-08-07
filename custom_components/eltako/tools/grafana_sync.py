"""Push the Grafana dashboards of this integration into a Grafana instance.

The dashboards ship with the integration (`grafana/dashboards/*.json`) so that they are
versioned together with the data model they query - a new tag or field is useless without a
panel that shows it. Getting them into Grafana works two ways:

* **file provisioning** - Grafana reads the folder itself. Used by the dev container, which
  mounts `grafana/dashboards` into its provisioning path. Nothing to click, but it needs
  access to the file system of the Grafana host.
* **this module** - the dashboards are POSTed to the Grafana HTTP API. Works with any
  reachable Grafana (a NAS, a container, Grafana Cloud) and is what the button
  *Sync dashboards* in the web ui uses.

Both use the very same files, so a dashboard cannot drift between the two paths.

Grafana needs a service account token with the role *Editor*
(Administration -> Users and access -> Service accounts). `user:password` is accepted as
well and sent as basic auth, which is handy for a local test setup (admin:admin).

The datasource is matched by its **name** at sync time: the panels reference the uid
`eltako-influxdb`, and if no datasource with that uid exists the uid of the first InfluxDB
datasource is substituted. That way the dashboards also land in a Grafana whose InfluxDB was
created by hand.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request

from ..const import CONF_GRAFANA_TOKEN, CONF_GRAFANA_URL, INTEGRATION_DIR, LOGGER

LOG_PREFIX_GRAFANA = "Grafana Sync"

DASHBOARD_DIR = os.path.join(INTEGRATION_DIR, 'grafana', 'dashboards')

# uid the shipped dashboards reference. Replaced by the uid of an existing InfluxDB
# datasource if this one is not present.
DATASOURCE_UID = 'eltako-influxdb'

# folder the dashboards are created in
FOLDER_TITLE = 'Eltako'

REQUEST_TIMEOUT = 15


def load_dashboards() -> list[dict]:
    """The dashboards shipped with the integration, sorted by title."""
    dashboards = []
    if not os.path.isdir(DASHBOARD_DIR):
        return dashboards
    for name in sorted(os.listdir(DASHBOARD_DIR)):
        if not name.endswith('.json'):
            continue
        path = os.path.join(DASHBOARD_DIR, name)
        try:
            with open(path, encoding='utf-8') as handle:
                dashboard = json.load(handle)
        except (OSError, ValueError) as e:
            LOGGER.warning(f"[{LOG_PREFIX_GRAFANA}] Cannot read dashboard '{name}': {e}")
            continue
        dashboard['_file'] = name
        dashboards.append(dashboard)
    return dashboards


def describe_dashboards() -> list[dict]:
    """What the web ui shows before syncing: title, uid and number of panels."""
    return [{
        'file': dashboard['_file'],
        'uid': dashboard.get('uid'),
        'title': dashboard.get('title'),
        'panels': len(dashboard.get('panels') or []),
    } for dashboard in load_dashboards()]


### ---------------------------------------------------------------------------
### http helpers (no client library, plain urllib in an executor)
### ---------------------------------------------------------------------------

def _auth_header(token: str) -> dict:
    token = str(token or '').strip()
    if not token:
        return {}
    if ':' in token and not token.lower().startswith('glsa_'):
        encoded = base64.b64encode(token.encode()).decode()
        return {'Authorization': f'Basic {encoded}'}
    return {'Authorization': f'Bearer {token}'}


def _request(url: str, token: str, method: str = 'GET', payload: dict = None) -> tuple[int, dict]:
    data = None if payload is None else json.dumps(payload).encode()
    headers = {'Accept': 'application/json', **_auth_header(token)}
    if data is not None:
        headers['Content-Type'] = 'application/json'

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            body = response.read().decode() or '{}'
            return response.status, json.loads(body)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors='replace')
        try:
            return e.code, json.loads(body or '{}')
        except ValueError:
            return e.code, {'message': body[:300]}


def _resolve_datasource_uid(base_url: str, token: str) -> str | None:
    """uid of the InfluxDB datasource the dashboards should query.

    Keeps DATASOURCE_UID if it exists. Otherwise the first InfluxDB datasource is used, so the
    dashboards work in a Grafana whose datasource was created by hand.
    """
    status, datasources = _request(f"{base_url}/api/datasources", token)
    if status != 200 or not isinstance(datasources, list):
        return None

    for datasource in datasources:
        if datasource.get('uid') == DATASOURCE_UID:
            return DATASOURCE_UID
    for datasource in datasources:
        if str(datasource.get('type')) == 'influxdb':
            return datasource.get('uid')
    return None


def _retarget(node, uid: str) -> None:
    """Point every datasource reference of a dashboard at `uid` (in place)."""
    if isinstance(node, dict):
        if node.get('type') == 'influxdb' and 'uid' in node:
            node['uid'] = uid
        elif set(node) >= {'uid'} and node.get('uid') == DATASOURCE_UID:
            node['uid'] = uid
        for value in node.values():
            _retarget(value, uid)
    elif isinstance(node, list):
        for value in node:
            _retarget(value, uid)


def _ensure_folder(base_url: str, token: str) -> str | None:
    """uid of the Eltako folder, created if it does not exist yet."""
    status, folders = _request(f"{base_url}/api/folders", token)
    if status == 200 and isinstance(folders, list):
        for folder in folders:
            if str(folder.get('title')) == FOLDER_TITLE:
                return folder.get('uid')

    status, created = _request(f"{base_url}/api/folders", token, 'POST', {'title': FOLDER_TITLE})
    if status in (200, 201) and isinstance(created, dict):
        return created.get('uid')
    # 409/412 = the folder exists but was not listed (restricted permissions) - not fatal,
    # the dashboards then land in the default folder
    LOGGER.debug(f"[{LOG_PREFIX_GRAFANA}] Cannot create the folder '{FOLDER_TITLE}' "
                 f"(status {status}) - using the default folder.")
    return None


### ---------------------------------------------------------------------------
### the sync itself
### ---------------------------------------------------------------------------

def sync(general_settings: dict) -> dict:
    """Push all shipped dashboards. Blocking - call it in an executor.

    Returns a result for the web ui: what was synced, what failed and why. Never raises.
    """
    base_url = str(general_settings.get(CONF_GRAFANA_URL, '') or '').strip().rstrip('/')
    token = str(general_settings.get(CONF_GRAFANA_TOKEN, '') or '').strip()

    if not base_url:
        return {'success': False, 'error': "No Grafana URL configured (see the settings on the "
                                           "about page).", 'dashboards': []}

    dashboards = load_dashboards()
    if not dashboards:
        return {'success': False, 'error': f"No dashboard found in {DASHBOARD_DIR}.",
                'dashboards': []}

    status, health = _request(f"{base_url}/api/health", token)
    if status != 200:
        return {'success': False, 'dashboards': [],
                'error': f"Grafana at {base_url} did not answer (status {status}). "
                         f"{health.get('message', '')}".strip()}

    datasource_uid = _resolve_datasource_uid(base_url, token)
    if datasource_uid is None:
        return {'success': False, 'dashboards': [],
                'error': "No InfluxDB datasource found in Grafana. Create one (or check the api "
                         "token - listing datasources needs a token with the role 'Editor')."}

    folder_uid = _ensure_folder(base_url, token)

    results = []
    for dashboard in dashboards:
        title = dashboard.get('title') or dashboard['_file']
        payload_dashboard = {key: value for key, value in dashboard.items() if key != '_file'}
        _retarget(payload_dashboard, datasource_uid)
        payload_dashboard.pop('id', None)        # let grafana assign it

        payload = {'dashboard': payload_dashboard, 'overwrite': True,
                   'message': 'synced by the Eltako integration'}
        if folder_uid:
            payload['folderUid'] = folder_uid

        status, body = _request(f"{base_url}/api/dashboards/db", token, 'POST', payload)
        ok = status in (200, 201)
        results.append({
            'title': title, 'uid': payload_dashboard.get('uid'), 'success': ok,
            'url': f"{base_url}{body.get('url')}" if ok and body.get('url') else None,
            'message': None if ok else f"status {status}: {body.get('message') or body}",
        })
        if not ok:
            LOGGER.warning(f"[{LOG_PREFIX_GRAFANA}] Cannot sync '{title}': "
                           f"status {status} - {body.get('message') or body}")

    synced = [result for result in results if result['success']]
    LOGGER.info(f"[{LOG_PREFIX_GRAFANA}] Synced {len(synced)}/{len(results)} dashboard(s) to "
                f"{base_url} (datasource {datasource_uid}).")

    return {
        'success': len(synced) == len(results),
        'grafana_url': base_url,
        'grafana_version': health.get('version'),
        'datasource_uid': datasource_uid,
        'folder': FOLDER_TITLE if folder_uid else None,
        'dashboards': results,
        'error': None if len(synced) == len(results)
                 else f"{len(results) - len(synced)} of {len(results)} dashboards failed.",
    }
