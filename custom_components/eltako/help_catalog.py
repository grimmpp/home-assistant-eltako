"""What this integration supports, compiled from the code instead of written down.

The help page of the web ui shows which devices, EEPs, gateways and platforms are supported.
Such a list rots the moment it is typed out by hand: a device added to the catalog or an EEP
added to eltakobus would silently stay missing. So nothing here is a literal list - everything
is derived from the modules which already are the source of truth:

* platforms and the EEPs they accept   -> the voluptuous schemas of schema.py
* every EEP that can be decoded        -> the profile registry of eltakobus
* devices                              -> DEVICE_CATALOG of device_catalog.py
* gateways                             -> GatewayDeviceType plus its catalog entries
* documentation and tutorials          -> the docs/ directory of the repository

The only literal data are the external links (forum, PCT14, ...) which exist nowhere in the
code, and the fallback repository url.
"""

from __future__ import annotations

import json
import os
import re

import voluptuous as vol
from eltakobus.eep import EEP

from . import device_catalog
from .const import CONF_EEP, CONF_SENDER, GatewayDeviceType, LOGGER, PLATFORMS

REPOSITORY_URL = 'https://github.com/grimmpp/home-assistant-eltako'

# Links to places outside of this repository. They are not derivable from anything.
EXTERNAL_LINKS: list[dict] = [
    {'title': 'Repository', 'url': REPOSITORY_URL, 'icon': 'mdi:github',
     'description': 'Source code, releases and issue tracker of this integration.'},
    {'title': 'Community forum',
     'url': 'https://community.home-assistant.io/t/eltako-baureihe-14-rs485-enocean-debugging/49712',
     'icon': 'mdi:forum-outline',
     'description': 'Discussion thread about Eltako series 14 in the Home Assistant forum.'},
    {'title': 'Eltako PCT14', 'url': 'https://www.eltako.com/en/software-pct14/', 'icon': 'mdi:tools',
     'description': 'Windows tool of Eltako to configure series 14 devices and their teach-in memory.'},
    {'title': 'EnOcean Device Manager', 'url': 'https://github.com/grimmpp/enocean-device-manager',
     'icon': 'mdi:file-tree',
     'description': 'Companion tool of the same author: reads a bus and generates the yaml for this integration.'},
    {'title': 'EnOcean Alliance - EEP specification',
     'url': 'https://www.enocean-alliance.org/what-is-enocean/specifications/', 'icon': 'mdi:file-certificate-outline',
     'description': 'The official EnOcean Equipment Profiles this integration implements.'},
    # eltako.com moved its product pages into a catalog with numeric category ids; the old
    # /en/product/... paths answer with 404. Category 16 is "Professional Smart Home", which
    # holds the series 14 and the wireless devices. Deep links of a single product still work.
    {'title': 'Eltako product catalog', 'url': 'https://www.eltako.com/en/catalog/categories/16/',
     'icon': 'mdi:factory',
     'description': 'Product pages of the devices supported here: Professional Smart Home with the series 14.'},
]

# A readme without its own heading gets its directory name prettified.
_DOC_TITLE_OVERRIDES = {
    'faq': 'FAQ',
    'web-ui': 'Web UI',
    'dev-container': 'Dev container',
    'grafana': 'Grafana',
}

_HEADING = re.compile(r'^\s{0,3}#\s+(.+?)\s*#*\s*$', re.MULTILINE)

# Generated list of the documentation. It ships with the integration because HACS installs
# custom_components/eltako/ only - see get_documentation().
DOCS_INDEX_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'docs_index.json')


# --------------------------------------------------------------------------- platforms
def _collect_eeps(node, in_sender: bool = False, found: dict = None) -> dict:
    """Pull the accepted EEPs out of a voluptuous schema.

    Reading them from a class attribute would need every schema to spell its list the same
    way, and they do not: the binary sensor keeps it in a module constant, the climate schema
    calls it CONF_CLIMATE_EEP. The validator itself is unambiguous - `vol.In([...])` behind
    the `eep` key - so the schema tree is walked instead. EEPs below a `sender` key are what
    Home Assistant sends *with*, not what the device speaks.
    """
    if found is None:
        found = {'eep': set(), 'sender_eep': set()}

    if isinstance(node, (vol.All, vol.Any)):
        for validator in node.validators:
            _collect_eeps(validator, in_sender, found)
    elif isinstance(node, vol.Schema):
        _collect_eeps(node.schema, in_sender, found)
    elif isinstance(node, dict):
        for key, value in node.items():
            name = str(key)
            _collect_eeps(value, in_sender or name == CONF_SENDER, found)
            if name == CONF_EEP and isinstance(value, vol.In):
                target = 'sender_eep' if in_sender else 'eep'
                found[target].update(str(entry) for entry in value.container)
    elif isinstance(node, (list, tuple)):
        for value in node:
            _collect_eeps(value, in_sender, found)

    return found


def _platform_schemas() -> list:
    """Entity platform schemas, found through the abstract base class.

    A new platform is picked up automatically. `PLATFORMS` of the integration is the filter:
    the gateway and the general settings are schemas as well, but they configure the
    integration instead of producing entities.
    """
    from . import schema

    entity_platforms = {str(platform) for platform in PLATFORMS}
    found = []
    for candidate in schema.EltakoPlatformSchema.__subclasses__():
        platform = str(getattr(candidate, 'PLATFORM', '') or '')
        if platform not in entity_platforms or getattr(candidate, 'ENTITY_SCHEMA', None) is None:
            continue
        found.append((platform, candidate))
    return sorted(found, key=lambda item: item[0])


def get_platforms() -> list[dict]:
    """Entity platforms with the EEPs their schema accepts."""
    platforms = []
    for platform, definition in _platform_schemas():
        eeps = _collect_eeps(definition.ENTITY_SCHEMA)
        platforms.append({
            'platform': platform,
            'eeps': sorted(eeps['eep']),
            'sender_eeps': sorted(eeps['sender_eep']),
            'description': (definition.__doc__ or '').strip().splitlines()[0] if definition.__doc__ else '',
        })
    return platforms


# --------------------------------------------------------------------------- EEPs
def _known_eep_strings() -> list[str]:
    """Every EEP eltakobus can decode.

    The registry attribute of the library is name mangled and carries a typo
    (`_EEP__sublasses_by_string`), so it is read defensively and the class tree is used as
    the fallback - if the library renames it, the list stays complete instead of empty.
    """
    registry = getattr(EEP, '_EEP__sublasses_by_string', None)
    if isinstance(registry, dict) and registry:
        return sorted(str(name) for name in registry)

    LOGGER.debug('[Help] EEP registry of eltakobus not found - deriving from the class tree.')
    seen, pending = set(), list(EEP.__subclasses__())
    while pending:
        profile = pending.pop()
        pending.extend(profile.__subclasses__())
        name = getattr(profile, 'eep_string', None) or profile.__name__.replace('_', '-')
        if re.fullmatch(r'[0-9A-Fa-f]{2}-[0-9A-Fa-f]{2}-[0-9A-Fa-f]{2}', str(name)):
            seen.add(str(name).upper())
    return sorted(seen)


def _eep_description(eep_string: str) -> str:
    """First line of the profile's docstring - the library documents them there."""
    try:
        profile = EEP.find(eep_string)
    except Exception:                      # noqa: BLE001 - an unknown profile is not an error here
        return ''
    for line in (profile.__doc__ or '').strip().splitlines():
        if line.strip():
            return line.strip()
    return ''


def get_eeps() -> list[dict]:
    """All EEPs, each with what it is, which platforms take it and which devices use it."""
    by_platform: dict[str, list[str]] = {}
    by_platform_sender: dict[str, list[str]] = {}
    for platform, definition in _platform_schemas():
        accepted = _collect_eeps(definition.ENTITY_SCHEMA)
        for eep in accepted['eep']:
            by_platform.setdefault(str(eep).upper(), []).append(platform)
        for eep in accepted['sender_eep']:
            by_platform_sender.setdefault(str(eep).upper(), []).append(platform)

    devices_by_eep: dict[str, set[str]] = {}
    for entry in device_catalog.DEVICE_CATALOG:
        for key in ('eep', 'sender_eep'):
            if entry.get(key):
                devices_by_eep.setdefault(str(entry[key]).upper(), set()).add(entry['hw_type'])

    # everything the library knows plus everything the catalog references - a device may name
    # an EEP the installed eltakobus does not implement, and that gap should be visible
    names = set(_known_eep_strings()) | set(devices_by_eep) | set(by_platform) | set(by_platform_sender)

    eeps = []
    for name in sorted(names):
        platforms = sorted(set(by_platform.get(name, [])))
        sender_platforms = sorted(set(by_platform_sender.get(name, [])))
        eeps.append({
            'eep': name,
            'rorg': name.split('-')[0] if '-' in name else '',
            'description': _eep_description(name),
            'platforms': platforms,
            'sender_platforms': sender_platforms,
            'devices': sorted(devices_by_eep.get(name, [])),
            'decodable': name in set(_known_eep_strings()),
            # an EEP no platform accepts can still be recorded and analysed, it just cannot
            # become an entity
            'usable_as_entity': bool(platforms),
        })
    return eeps


# --------------------------------------------------------------------------- devices
def get_devices() -> list[dict]:
    """The device catalog, one entry per hardware type.

    A device appears once even when it speaks several EEPs (FTS14EM, F3Z14D, FLGTF); its
    profiles are collected into the entry.
    """
    devices: dict[str, dict] = {}
    for entry in device_catalog.DEVICE_CATALOG:
        hw_type = entry['hw_type']
        device = devices.setdefault(hw_type, {
            'hw_type': hw_type,
            'brand': entry.get('brand', ''),
            'description': entry.get('description', ''),
            'bus_device': bool(entry.get('bus_device')),
            'is_gateway': bool(entry.get('gateway_type')),
            'address_count': entry.get('address_count'),
            'docs': entry.get('docs'),
            'profiles': [],
            'platforms': [],
        })
        if entry.get('eep'):
            device['profiles'].append({
                'eep': entry['eep'],
                'sender_eep': entry.get('sender_eep'),
                'platform': entry.get('platform'),
                'description': entry.get('description', ''),
            })
        if entry.get('platform') and entry['platform'] not in device['platforms']:
            device['platforms'].append(entry['platform'])
        # the widest address count wins - it is what the device occupies on the bus
        if entry.get('address_count') and (device['address_count'] or 0) < entry['address_count']:
            device['address_count'] = entry['address_count']

    return sorted(devices.values(), key=lambda device: (not device['is_gateway'], device['hw_type']))


# --------------------------------------------------------------------------- gateways
def get_gateways() -> list[dict]:
    """Supported gateway types.

    `GatewayDeviceType` carries several aliases for the same value (EltakoFAM14 and
    GatewayEltakoFAM14 are both 'fam14'); iterating an enum yields the canonical members
    only, so each gateway appears once.
    """
    gateways = []
    for gateway_type in GatewayDeviceType:
        entry = device_catalog.describe_gateway_type(gateway_type.value)
        gateways.append({
            'gateway_type': gateway_type.value,
            'name': gateway_type.name,
            'hw_type': entry.get('hw_type', ''),
            'brand': entry.get('brand', ''),
            'description': entry.get('description', ''),
            'protocol': 'ESP2' if GatewayDeviceType.is_esp2_gateway(gateway_type) else 'ESP3',
            'bus_gateway': bool(GatewayDeviceType.is_bus_gateway(gateway_type)),
            'transceiver': bool(GatewayDeviceType.is_transceiver(gateway_type)),
            'lan': bool(GatewayDeviceType.is_lan_gateway(gateway_type)),
            'docs': entry.get('docs') or device_catalog.GATEWAY_DOCS,
        })
    return sorted(gateways, key=lambda gateway: gateway['gateway_type'])


# --------------------------------------------------------------------------- documentation
def _repository_root() -> str:
    """custom_components/eltako/ -> the checkout root."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _title_of(path: str, fallback: str) -> str:
    try:
        with open(path, encoding='utf-8') as handle:
            heading = _HEADING.search(handle.read(4096))
    except OSError:
        return fallback
    if heading:
        # strip markdown links and images which some readmes carry in their heading
        title = re.sub(r'!?\[([^\]]*)\]\([^)]*\)', r'\1', heading.group(1)).strip()
        if title:
            return title
    return fallback


def scan_documentation() -> list[dict]:
    """Read the docs/ directory of the checkout: one entry per document, heading as the title.

    Only available where the repository is checked out. `get_documentation()` is what the
    catalog uses - see DOCS_INDEX_FILE for why.
    """
    docs_dir = os.path.join(_repository_root(), 'docs')
    if not os.path.isdir(docs_dir):
        return []

    documents = []
    try:
        names = sorted(os.listdir(docs_dir))
    except OSError as error:
        LOGGER.debug('[Help] Could not read the docs directory: %s', error)
        return []

    for name in names:
        path = os.path.join(docs_dir, name)

        if os.path.isdir(path):
            readme = next((os.path.join(path, candidate) for candidate in ('readme.md', 'README.md')
                           if os.path.isfile(os.path.join(path, candidate))), None)
            if readme is None:
                continue
            relative = os.path.relpath(readme, _repository_root()).replace(os.sep, '/')
            fallback = _DOC_TITLE_OVERRIDES.get(name, name.replace('_', ' ').replace('-', ' ').strip().capitalize())
        elif name.lower().endswith('.md') and name.lower() != 'readme.md':
            relative = f'docs/{name}'
            fallback = _DOC_TITLE_OVERRIDES.get(
                name[:-3], name[:-3].replace('_', ' ').replace('-', ' ').strip().capitalize())
        else:
            continue

        documents.append({
            'title': _title_of(os.path.join(_repository_root(), relative), fallback),
            'path': relative,
            'section': name,
        })

    return sorted(documents, key=lambda document: document['title'].lower())


def _load_documentation_index() -> list[dict]:
    """The index shipped inside the integration."""
    try:
        with open(DOCS_INDEX_FILE, encoding='utf-8') as handle:
            index = json.load(handle)
    except (OSError, ValueError) as error:
        LOGGER.debug('[Help] Could not read %s: %s', DOCS_INDEX_FILE, error)
        return []
    documents = index.get('documents') if isinstance(index, dict) else index
    return documents if isinstance(documents, list) else []


def get_documentation(base_url: str = None) -> list[dict]:
    """The documentation of the project, as links into the repository.

    Adding a tutorial to docs/ makes it show up here - nothing has to be registered. But HACS
    installs only `custom_components/eltako/`, so on a normal installation there is no docs
    directory to scan and the page would list nothing at all. The scan result is therefore
    generated into DOCS_INDEX_FILE, which ships with the integration; the live scan wins
    wherever the checkout is available (development, the dev container mounting the repo).

    test_help_catalog.py compares the shipped index against a fresh scan, so it cannot go
    stale - regenerate it with `python -m custom_components.eltako.help_catalog`.
    """
    base_url = (base_url or f'{REPOSITORY_URL}/tree/main').rstrip('/')
    documents = scan_documentation() or _load_documentation_index()
    return [{**document, 'url': f"{base_url}/{document['path']}"} for document in documents]


def write_documentation_index() -> str:
    """Regenerate the shipped index from the checkout. Returns the file it wrote."""
    documents = scan_documentation()
    if not documents:
        raise RuntimeError(f'No docs directory below {_repository_root()} - nothing to write.')

    with open(DOCS_INDEX_FILE, 'w', encoding='utf-8') as handle:
        json.dump({'comment': 'Generated by help_catalog.write_documentation_index() - do not edit.',
                   'documents': documents}, handle, indent=2, ensure_ascii=False)
        handle.write('\n')
    return DOCS_INDEX_FILE


# --------------------------------------------------------------------------- everything
def build_catalog(base_url: str = None) -> dict:
    """The whole payload of the help page."""
    eeps = get_eeps()
    devices = get_devices()
    gateways = get_gateways()
    documentation = get_documentation(base_url)
    platforms = get_platforms()

    return {
        'repository': REPOSITORY_URL,
        'platforms': platforms,
        'eeps': eeps,
        'devices': devices,
        'gateways': gateways,
        'documentation': documentation,
        'links': EXTERNAL_LINKS,
        'summary': {
            'device_count': len(devices),
            'eep_count': len(eeps),
            'decodable_eep_count': sum(1 for eep in eeps if eep['decodable']),
            'entity_eep_count': sum(1 for eep in eeps if eep['usable_as_entity']),
            'gateway_count': len(gateways),
            'platform_count': len(platforms),
            'document_count': len(documentation),
            'bus_device_count': sum(1 for device in devices if device['bus_device']),
        },
    }


if __name__ == '__main__':                                          # pragma: no cover
    print(f'Wrote {write_documentation_index()}')
