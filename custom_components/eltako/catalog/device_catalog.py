"""Compatibility adapter for the device catalog supplied by ``eltako14bus``.

The catalog is maintained by the bus library since v1.0.0.  This module remains as a
small import-compatible shim for integrations and third-party consumers which used the
old Home Assistant path.
"""

from eltakobus.device_catalog import (  # noqa: F401
    DEVICE_CATALOG,
    as_display_text,
    catalog_eep_references,
    describe_gateway_type,
    describe_hw_type as _library_describe_hw_type,
    devices_for_eep,
    eep_device_mapping,
    entries_for_hw_type,
    find_hw_type as _library_find_hw_type,
    get_device_templates as _library_get_device_templates,
    normalize_hw_type,
)

# Documentation links are integration metadata, not part of the reusable library catalog.
GATEWAY_DOCS = 'https://github.com/grimmpp/home-assistant-eltako/tree/main/docs/gateways'


# Products named in the ELTAKO technical catalogue (Kapitel T) whose telegram
# profile is implemented by eltako14bus v1.0.0. The reusable library keeps the
# protocol catalog independent of this product/documentation list; these rows
# are therefore integration metadata layered on top of it.
PDF_DEVICE_CATALOG_ADDITIONS: list[dict] = [
    # Sensors and transmitters
    *[{'hw_type': name, 'brand': 'ELTAKO', 'description': 'Temperature sensor',
       'platform': 'sensor', 'eep': eep, 'address_count': 1}
      for name, eep in (
          ('FTF65S', 'A5-02-05'), ('FMMS44SB', 'A5-02-05'), ('FMS55SB', 'A5-02-05'),
          ('FMS55ESB', 'A5-02-05'), ('FMS65ESB', 'A5-02-05'),
          ('FFT65B', 'A5-04-02'), ('FFTF65B', 'A5-04-02'), ('FFT55B', 'A5-04-02'),
          ('FTFB', 'A5-04-02'), ('FTFSB', 'A5-04-02'), ('FFT60SB', 'A5-04-02'),
          ('FLGTF65', 'A5-04-02'), ('FLGTF55', 'A5-04-02'),
          ('FBH65SB', 'A5-04-03'), ('FBH55SB', 'A5-04-03'), ('FBHF65SB', 'A5-04-03'),
          ('FAH65S', 'A5-06-01'), ('FIH65S', 'A5-06-01'), ('FHD60SB', 'A5-06-01'),
          ('FHD65SB', 'A5-06-02'),
          ('FABH65S', 'A5-08-01'), ('FBH65', 'A5-08-01'), ('FBH65S', 'A5-08-01'),
          ('FBH65TF', 'A5-08-01'), ('FB65B', 'A5-08-01'), ('FB55B', 'A5-08-01'),
          ('FBH65SB', 'A5-08-01'), ('FBH55SB', 'A5-08-01'), ('FBHF65SB', 'A5-08-01'),
          ('FIH65B', 'A5-06-02'),
          ('FCO2TF65', 'A5-09-04'), ('FCO2TS', 'A5-09-04'),
          ('FLT58', 'A5-09-05'), ('FLGTF65', 'A5-09-0C'), ('FLGTF55', 'A5-09-0C'),
          ('FTR78S', 'A5-10-03'), ('FTR86B', 'A5-10-06'),
          ('FTR65DSB', 'A5-10-06'), ('FTR55DSB', 'A5-10-06'), ('FTR65HB', 'A5-10-06'),
          ('FTRF65HB', 'A5-10-06'), ('FTR55HB', 'A5-10-06'), ('FTR65SB', 'A5-10-06'),
          ('FTRF65SB', 'A5-10-06'), ('FTR55SB', 'A5-10-06'), ('FTR65HS', 'A5-10-06'),
          ('FTAF65D', 'A5-10-06'), ('FUTH65D', 'A5-10-06'), ('FUTH55D', 'A5-10-06'),
          ('FUTH65D', 'A5-10-12'), ('FUTH55D', 'A5-10-12'),
          ('FWS61', 'A5-13-01'),
          ('FKS-H', 'A5-20-04'), ('FSM60B', 'A5-30-01'), ('FHMB', 'A5-30-03'),
          ('FRWB', 'A5-30-03'),
          ('FNS55B', 'F6-01-01'), ('FNS55EB', 'F6-01-01'), ('FNS65EB', 'F6-01-01'),
          ('FSTAP', 'A5-10-03'),
          ('FASM60', 'F6-10-00'), ('FSM14', 'F6-10-00'), ('FSM61', 'F6-10-00'),
          ('FTK', 'D5-00-01'), ('FTKB-RW', 'D5-00-01'), ('FFKB', 'D5-00-01'),
          ('FTKB-gr', 'D5-00-01'), ('FTKE', 'F6-10-00'), ('FFTE', 'F6-10-00'),
          ('F1T65', 'F6-01-01'), ('F1FT65', 'F6-01-01'), ('F1T55E', 'F6-01-01'),
          ('FET55E', 'F6-01-01'), ('FKD', 'F6-01-01'), ('FMH1W', 'F6-01-01'),
          ('F4T65', 'F6-02-01'), ('F4T65B', 'F6-02-01'), ('F4FT65', 'F6-02-01'),
          ('F4FT65B', 'F6-02-01'), ('F4PT', 'F6-02-01'), ('FT4F', 'F6-02-01'),
          ('F4T55E', 'F6-02-01'), ('F4T55EB', 'F6-02-01'), ('F4PT55', 'F6-02-01'),
          ('FHS4', 'F6-02-01'), ('FMH4', 'F6-02-01'), ('FMH4S', 'F6-02-01'),
          ('FF8', 'F6-02-01'), ('FMH8', 'F6-02-01'), ('F4T55B', 'F6-02-01'),
          ('FT55', 'F6-02-01'), ('FS55', 'F6-02-01'), ('FS55E', 'F6-02-01'),
          ('FS65E', 'F6-02-01'),
      )],
    # Additional wireless devices listed in Kapitel T. These products use EEPs for which
    # the integration already has a binary-sensor, sensor or light platform.
    *[{'hw_type': name, 'brand': 'ELTAKO', 'description': 'Wireless pushbutton',
       'platform': 'binary_sensor', 'eep': 'F6-01-01', 'address_count': 1}
      for name in ('FPE-1', 'FTTB')],
    *[{'hw_type': name, 'brand': 'ELTAKO', 'description': 'Wireless rocker switch',
       'platform': 'binary_sensor', 'eep': 'F6-02-01', 'address_count': 1}
      for name in ('F2T65', 'F2T65B', 'F2FT65', 'F2FT65B', 'F2ZT65', 'F2FZT65B',
                   'F2T55E', 'F2T55EB', 'F2ZT55E', 'FZT55', 'FHS2', 'FMH2', 'FMH2S',
                   'F6T65B', 'F6T55B')],
    *[{'hw_type': name, 'brand': 'ELTAKO', 'description': 'Occupancy sensor',
       'platform': 'binary_sensor', 'eep': 'A5-07-01', 'address_count': 1}
      for name in ('FABH130', 'FB65B', 'FB55B', 'FBH65SB', 'FBH55SB', 'FBHF65SB')],
    *[{'hw_type': name, 'brand': 'ELTAKO', 'description': 'Temperature and humidity sensor',
       'platform': 'sensor', 'eep': 'A5-04-03', 'address_count': 1}
      for name in ('FFT65B', 'FFTF65B', 'FFT55B', 'FTFB', 'FTFSB', 'FFT60SB')],
    *[{'hw_type': name, 'brand': 'ELTAKO', 'description': 'Electricity meter',
       'platform': 'sensor', 'eep': 'A5-12-01', 'address_count': 1}
      for name in ('FWZ14', 'FWZ12', 'DSZ14DRS', 'DSZ14WDRS', 'FSR61VA', 'FSVA-230V')],
    *[{'hw_type': name, 'brand': 'ELTAKO', 'description': 'Light actuator',
       'platform': 'light', 'eep': 'A5-38-08', 'sender_eep': 'A5-38-08',
       'address_count': 1}
      for name in ('FDT55B', 'FDT55EB', 'FDT65B', 'FDTF65B', 'FZK14', 'FHD62NP',
                   'FLC61', 'FMS61NP-230V', 'FMZ61-230V', 'FSR70S-230V',
                   'FUD70S-230V', 'FZK61NP-230V')],
    *[{'hw_type': name, 'brand': 'ELTAKO', 'description': 'Cover actuator',
       'platform': 'cover', 'eep': 'G5-3F-7F', 'sender_eep': 'H5-3F-7F',
       'address_count': 1}
      for name in ('FRGBW71L', 'FWWKW71L')],
    *[{'hw_type': name, 'brand': 'ELTAKO', 'description': 'Light actuator',
       'platform': 'light', 'eep': 'A5-38-08', 'sender_eep': 'A5-38-08',
       'address_count': 1}
      for name in ('FDG71L', 'FLC61NP', 'FMS61', 'FSR14SSR', 'FSR61/8-24V',
                   'FUD61', 'FSUD-230V')],
    *[{'hw_type': name, 'brand': 'ELTAKO', 'description': 'Heating/Cooling',
       'platform': 'climate', 'eep': 'A5-10-06', 'sender_eep': 'A5-10-06',
       'address_count': 1}
      for name in ('FAE14LPR', 'FHK61U')],
    *[{'hw_type': name, 'brand': 'ELTAKO', 'description': 'Electricity meter',
       'platform': 'sensor', 'eep': 'A5-12-01', 'address_count': 1}
      for name in ('FSR61VA-10A',)],
    *[{'hw_type': name, 'brand': 'ELTAKO', 'description': 'Multisensor',
       'platform': 'sensor', 'eep': eep, 'address_count': 1}
      for name in ('FMMS44SB', 'FMS55SB', 'FMS55ESB', 'FMS65ESB')
      for eep in ('A5-04-01', 'A5-04-03', 'A5-06-02', 'A5-06-03')],
    # Actuators using the Eltako command/status profiles documented in Kap. T.
    *[{'hw_type': name, 'brand': 'ELTAKO', 'description': description,
       'platform': platform, 'eep': eep, 'sender_eep': sender, 'address_count': 1}
      for name, description, platform, eep, sender in (
          ('F2L14', 'Relay', 'light', 'M5-38-08', 'A5-38-08'),
          ('FFR14', 'Relay', 'light', 'M5-38-08', 'A5-38-08'),
          ('FMS14', 'Relay', 'light', 'M5-38-08', 'A5-38-08'),
          ('FTN14', 'Relay', 'light', 'M5-38-08', 'A5-38-08'),
          ('FAE14', 'Relay', 'light', 'M5-38-08', 'A5-38-08'),
          ('F4SR14-LED', 'Relay', 'light', 'M5-38-08', 'A5-38-08'),
          ('FHK61', 'Heating/Cooling', 'climate', 'A5-10-06', 'A5-10-06'),
          ('FHK61SSR', 'Heating/Cooling', 'climate', 'A5-10-06', 'A5-10-06'),
          ('FHK61U-230V', 'Heating/Cooling', 'climate', 'A5-10-06', 'A5-10-06'),
          ('FSUD', 'Light dimmer', 'light', 'A5-38-08', 'A5-38-08'),
          ('FUD70S', 'Light dimmer', 'light', 'A5-38-08', 'A5-38-08'),
          ('FUD70S-230V', 'Light dimmer', 'light', 'A5-38-08', 'A5-38-08'),
          ('FDG71', 'Light dimmer', 'light', 'A5-38-08', 'A5-38-08'),
          ('FSG71/1-10V', 'Light dimmer', 'light', 'A5-38-08', 'A5-38-08'),
          ('FKLD61', 'Light dimmer', 'light', 'A5-38-08', 'A5-38-08'),
          ('FDH62', 'Light dimmer', 'light', 'A5-38-08', 'A5-38-08'),
          ('FLD61', 'Light dimmer', 'light', 'A5-38-08', 'A5-38-08'),
          ('FUD71', 'Light dimmer', 'light', 'A5-38-08', 'A5-38-08'),
          ('FUD71L', 'Light dimmer', 'light', 'A5-38-08', 'A5-38-08'),
          ('FUD61NP', 'Light dimmer', 'light', 'A5-38-08', 'A5-38-08'),
          ('FUD61NPN', 'Light dimmer', 'light', 'A5-38-08', 'A5-38-08'),
          ('FSR61', 'Relay', 'light', 'M5-38-08', 'A5-38-08'),
          ('FSR61NP', 'Relay', 'light', 'M5-38-08', 'A5-38-08'),
          ('FSR61G', 'Relay', 'light', 'M5-38-08', 'A5-38-08'),
          ('FSR61LN', 'Relay', 'light', 'M5-38-08', 'A5-38-08'),
          ('FSR71', 'Relay', 'light', 'M5-38-08', 'A5-38-08'),
          ('FSR71NP-4x', 'Relay', 'light', 'M5-38-08', 'A5-38-08'),
          ('FSR70S', 'Relay', 'light', 'M5-38-08', 'A5-38-08'),
          ('FSSA', 'Relay', 'light', 'M5-38-08', 'A5-38-08'),
          ('FSSG', 'Relay', 'light', 'M5-38-08', 'A5-38-08'),
          ('FSVA', 'Relay', 'light', 'M5-38-08', 'A5-38-08'),
          ('FSHA', 'Relay', 'light', 'M5-38-08', 'A5-38-08'),
          ('FSHA-230V', 'Relay', 'light', 'M5-38-08', 'A5-38-08'),
          ('FUA12-230V', 'Relay', 'light', 'M5-38-08', 'A5-38-08'),
          ('FTN61', 'Relay', 'light', 'M5-38-08', 'A5-38-08'),
          ('FHK61SSR-230V', 'Heating/Cooling', 'climate', 'A5-10-06', 'A5-10-06'),
          ('FLC61NP-230V', 'Relay', 'light', 'M5-38-08', 'A5-38-08'),
          ('FSVA-230V', 'Relay', 'light', 'M5-38-08', 'A5-38-08'),
          ('FTN61NP-230V', 'Relay', 'light', 'M5-38-08', 'A5-38-08'),
          ('FD62NP-230V', 'Light dimmer', 'light', 'A5-38-08', 'A5-38-08'),
          ('FD62NPN-230V', 'Light dimmer', 'light', 'A5-38-08', 'A5-38-08'),
          ('FJ62/12-36V DC', 'Cover', 'cover', 'G5-3F-7F', 'H5-3F-7F'),
          ('FJ62NP-230V', 'Cover', 'cover', 'G5-3F-7F', 'H5-3F-7F'),
          ('FSB61', 'Cover', 'cover', 'G5-3F-7F', 'H5-3F-7F'),
          ('FSB61NP', 'Cover', 'cover', 'G5-3F-7F', 'H5-3F-7F'),
          ('FSB71', 'Cover', 'cover', 'G5-3F-7F', 'H5-3F-7F'),
          ('FSB71NP', 'Cover', 'cover', 'G5-3F-7F', 'H5-3F-7F'),
          ('FR62', 'Relay', 'light', 'M5-38-08', 'A5-38-08'),
          ('FR62NP', 'Relay', 'light', 'M5-38-08', 'A5-38-08'),
          ('FL62', 'Relay', 'light', 'M5-38-08', 'A5-38-08'),
          ('FL62NP', 'Relay', 'light', 'M5-38-08', 'A5-38-08'),
          ('FZK61NP', 'Relay', 'light', 'M5-38-08', 'A5-38-08'),
          ('FZK61NP-230V', 'Relay', 'light', 'M5-38-08', 'A5-38-08'),
          ('FHK61-230V', 'Heating/Cooling', 'climate', 'A5-10-06', 'A5-10-06'),
      )],
    *[{'hw_type': 'FFGB-hg', 'brand': 'ELTAKO', 'description': 'Window/door contact',
       'platform': 'binary_sensor', 'eep': eep, 'address_count': 1}
      for eep in ('A5-14-09', 'A5-14-0A')],
    *[{'hw_type': name, 'brand': 'ELTAKO', 'description': description,
       'platform': 'binary_sensor', 'eep': eep, 'address_count': 1}
      for name, description, eep in (
          ('FFG7B', 'Window/door contact', 'A5-14-09'),
          ('FFG7B', 'Window/door contact', 'F6-10-00'),
          ('mTronic', 'Window/door contact', 'A5-14-0A'),
          ('FWS81', 'Water leakage detector', 'F6-05-01'),
          ('FZS65', 'Smoke detector', 'F6-05-02'),
      )],
]

# Keep one row per product/profile pair while preserving the library catalog order.
_catalog_rows = list(DEVICE_CATALOG)
_catalog_keys = {(row.get('hw_type'), row.get('eep'), row.get('sender_eep'))
                 for row in _catalog_rows}
for _row in PDF_DEVICE_CATALOG_ADDITIONS:
    _key = (_row.get('hw_type'), _row.get('eep'), _row.get('sender_eep'))
    if _key not in _catalog_keys:
        _catalog_rows.append(_row)
        _catalog_keys.add(_key)
DEVICE_CATALOG = _catalog_rows


def find_hw_type(name: str | None) -> dict:
    """Find a library or PDF-catalog product, including normalized aliases."""
    found = _library_find_hw_type(name)
    if found:
        return found
    wanted = normalize_hw_type(name)
    return next((row for row in DEVICE_CATALOG
                 if normalize_hw_type(row.get('hw_type')) == wanted), {})


def describe_hw_type(hw_type: str | None) -> dict:
    """Return the primary row for a library or PDF-catalog product."""
    found = _library_describe_hw_type(hw_type)
    return found or find_hw_type(hw_type)


def get_device_templates(platform: str, supported_eeps: list[str] = None,
                          supported_sender_eeps: list[str] = None) -> list[dict]:
    """Return templates from the library catalog plus the PDF additions."""
    templates = _library_get_device_templates(platform, supported_eeps, supported_sender_eeps)
    known = {template['value'] for template in templates}
    for entry in DEVICE_CATALOG:
        if entry.get('platform') != platform or not entry.get('eep'):
            continue
        if supported_eeps is not None and entry['eep'] not in supported_eeps:
            continue
        sender = entry.get('sender_eep')
        if sender and supported_sender_eeps is not None and sender not in supported_sender_eeps:
            sender = None
        value = f"{entry['hw_type']}|{entry['eep']}"
        if value in known:
            continue
        template = {'value': value, 'label': f"{entry['hw_type']} - {entry['description']}",
                    'hw_type': entry['hw_type'], 'description': entry['description'],
                    'eep': entry['eep']}
        if sender:
            template['sender_eep'] = sender
        if entry.get('address_count'):
            template['address_count'] = entry['address_count']
        templates.append(template)
    return sorted(templates, key=lambda template: template['label'])
