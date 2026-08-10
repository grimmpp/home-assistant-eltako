"""Which gateway switches an actuator - per device or for a whole bus.

An RS485 actuator only reacts to sender addresses which are in its own memory, and a
transceiver may only transmit senders out of **its** base id range. Both halves of that
sentence have to agree, otherwise a device is configured, listed and dead:

* the address has to be **in the actuator** - written over the bus, which only a FAM14 can do
* the same address has to be the **sender of the device in Home Assistant** - otherwise the
  integration transmits something the actuator does not listen to

Everything here does those two things together for one choice: pick a gateway for a device
(or for every device of a bus) and it gets `base id of that gateway + the last byte of the
actuator address` - the rule of the EnOcean Device Manager, see
`observation.bus_members.sender_id_for_gateway` - written into the actuator and stored as its
sender. The default is the bus itself (the FAM14): there the local sender ids `00-00-B0-xx`
apply, the same convention the detection and the yaml import use.

Order matters: the actuator is written **first**, the configuration follows for the devices
which really took it. An extra address in a memory is harmless (nothing is removed, the old
sender keeps switching), a configured sender which is in no actuator is a device which
silently stops working.
"""

from __future__ import annotations

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.const import CONF_ID, CONF_NAME
from homeassistant.core import HomeAssistant

from ..const import CONF_EEP, CONF_SENDER, GatewayDeviceType, LOGGER, WS_DEVICE_SENDER_GATEWAY
from .device_config import (_find_gateway_entry, async_save_ui_devices, get_ui_devices,
                            normalize_address)

LOG_PREFIX_SENDER_GATEWAY = "Sender Gateway"


def is_bus_address(address: str) -> bool:
    """A position on the RS485 bus - 00-00-00-xx. Only those have a memory to write into."""
    parts = str(address or '').upper().split('-')
    return len(parts) == 4 and parts[:3] == ['00', '00', '00']


def base_id_of(gateway) -> str | None:
    """The wireless base id of a gateway as a string, None if it has none (yet)."""
    from eltakobus.util import b2s

    try:
        return b2s(gateway.base_id[0]) if getattr(gateway, 'base_id', None) else None
    except Exception:   # noqa: BLE001 - a gateway which never reported one has none to offer
        return None


def can_program(gateway) -> bool:
    """Only a FAM14 writes into the memory of a bus actuator.

    An FGW14-USB sits on the same bus and puts telegrams on it, but it can neither read nor
    program a device - trying anyway would run into one timeout per actuator.
    """
    return getattr(gateway, 'dev_type', None) in (GatewayDeviceType.GatewayEltakoFAM14,
                                                  GatewayDeviceType.EltakoFAM14)


def sender_id_for(target_gateway, device_address: str) -> str | None:
    """The address Home Assistant has to send with when `target_gateway` carries the command.

    The bus itself keeps the local senders (`00-00-B0-xx`, the FAM14 default); every wireless
    or LAN gateway hands out an address of its own base id range. None when it cannot be
    formed - see sender_id_for_gateway().
    """
    from ..observation.bus_members import sender_id_for_gateway
    from ..tools.plug_and_play import local_sender_id

    if not is_bus_address(device_address):
        return None
    position = int(str(device_address).upper().split('-')[3], 16)
    if GatewayDeviceType.is_bus_gateway(getattr(target_gateway, 'dev_type', None)):
        return local_sender_id(position)
    return sender_id_for_gateway(base_id_of(target_gateway), device_address)


def gateway_of_sender(gateways, gateway_id: int, sender_id: str):
    """Which gateway a configured sender address belongs to - the current choice of a device.

    A local sender (`00-00-…`) is the bus itself, everything else belongs to the gateway whose
    base id range it lies in. None when no configured gateway owns it: an address which was
    imported from somewhere else, or a gateway which was removed since.
    """
    sender = str(sender_id or '').upper()
    if not sender:
        return None
    if sender.startswith('00-00-'):
        return next((g for g in gateways if g.dev_id == gateway_id), None)
    for gateway in gateways:
        base_id = base_id_of(gateway)
        if base_id and str(base_id).upper()[:8] == sender[:8]:
            return gateway
    return None


def _address_int(address: str) -> int | None:
    from eltakobus.util import AddressExpression

    try:
        return int.from_bytes(AddressExpression.parse(str(address))[0], 'big')
    except Exception:   # noqa: BLE001 - not an address (empty, malformed, a local one)
        return None


def configured_senders(hass: HomeAssistant) -> set[int]:
    """Every sender address which is already in use, as numbers.

    A wireless actuator has no bus position to derive an offset from, so the next free address
    of the range has to be found - and "free" means: not the sender of another device.
    """
    from .device_config import _describe_devices

    used = set()
    for device in _describe_devices(hass):
        sender = device.get('sender') or {}
        number = _address_int(sender.get(CONF_ID)) if isinstance(sender, dict) else None
        if number is not None:
            used.add(number)
    return used


def radio_sender_id_for(target_gateway, gateways, current_sender_id: str = None,
                        used: set = ()) -> str | None:
    """The address a **wireless** actuator should be switched with by `target_gateway`.

    A bus actuator carries its own number: position 4 becomes base id + 4, and the actuator
    knows nothing else. A wireless actuator has no such number - it takes whatever address
    teaches itself into it - so the address is picked instead of derived:

    1. the offset the current sender has inside the range of **its** gateway, so a device which
       is moved from one gateway to another keeps its place (FF-AA-80-05 -> FF-C0-02-05), and
    2. otherwise the first free offset of the target range - free meaning no other configured
       device already sends with it.

    None when the gateway has no wireless base id, or when its 128 addresses are used up.
    """
    from eltakobus.util import AddressExpression, b2s

    base_id = base_id_of(target_gateway)
    if not base_id or not str(base_id).upper().startswith('FF'):
        return None
    base = int.from_bytes(AddressExpression.parse(str(base_id))[0], 'big')
    last = 0x7F - (base & 0xFF)     # a base id covers 128 addresses, counted from its own end
    if last < 1:
        return None

    used = set(used or ())
    kept = None
    owner = gateway_of_sender(gateways, None, current_sender_id)
    if owner is not None:
        owner_base = _address_int(base_id_of(owner))
        current = _address_int(current_sender_id)
        if owner_base is not None and current is not None and 0 <= current - owner_base <= last:
            kept = current - owner_base

    for offset in ([kept] if kept is not None else []) + list(range(1, last + 1)):
        if base + offset not in used:
            return b2s((base + offset).to_bytes(4, 'big'))
    return None


async def async_assign_radio_sender(hass: HomeAssistant, target_gateway, address: str,
                                    gateway_id: int = None, send_teach_in: bool = True) -> dict:
    """Let `target_gateway` switch a **wireless** actuator - and teach it in.

    There is no memory to write here: a wireless actuator learns the address which is sent to
    it while it is in teach-in mode. So this stores the new sender and sends the teach-in
    telegram of its profile **through the chosen gateway** - the device has to be in learn mode
    at that moment, which is what the web ui asks for before it calls this.
    """
    from ..catalog.teach_in import get_teach_in_payload, supports_teach_in_button
    from .device_config import _describe_devices

    described = next((device for device in _describe_devices(hass)
                      if str(device.get('address', '')).upper() == str(address).upper()
                      and (gateway_id is None or device.get('gateway_id') == gateway_id)), None)
    if described is None:
        return {'error': 'unknown_device', 'message': f"No configured device {address}."}
    if not described.get('editable'):
        return {'error': 'not_editable',
                'message': f"{address} comes from configuration.yaml - change its sender there."}

    sender = described.get('sender') or {}
    sender_eep = str(sender.get(CONF_EEP, '') or '')
    if not sender_eep:
        return {'error': 'no_sender',
                'message': f"{address} has no sender - only an actuator is switched by Home "
                           f"Assistant, and it needs an address to be switched with."}

    gateways = _all_gateways(hass)
    used = configured_senders(hass) - {_address_int(sender.get(CONF_ID))} - {None}
    sender_id = radio_sender_id_for(target_gateway, gateways, sender.get(CONF_ID), used)
    if sender_id is None:
        return {'error': 'no_base_id',
                'message': f"'{target_gateway.dev_name}' has no free wireless address - connect "
                           f"it once so that it reports its base id."}

    job = {'platform': described['platform'], 'address': str(address).upper(),
           'name': described.get('name'), 'sender_id': sender_id, 'sender_eep': sender_eep,
           'previous_sender_id': str(sender.get(CONF_ID, '') or '')}
    bus_gateway = next((g for g in gateways if g.dev_id == described['gateway_id']), None)
    if bus_gateway is None:
        return {'error': 'unknown_gateway',
                'message': f"The gateway of {address} is not set up in Home Assistant."}

    updated = await _async_store_senders(hass, bus_gateway, [job])
    answer = {'gateway_id': bus_gateway.dev_id, 'gateway_name': bus_gateway.dev_name,
              'target_gateway_id': target_gateway.dev_id,
              'target_gateway_name': target_gateway.dev_name,
              'base_id': base_id_of(target_gateway), 'kind': 'telegram',
              'results': [], 'updated': updated, 'skipped': []}

    if not send_teach_in:
        answer['results'] = [{**job, 'result': 'not_programmed'}]
        return answer
    if not supports_teach_in_button(sender_eep):
        # nothing to send: the device has to learn this address at itself. The sender is
        # stored anyway - that is the half which Home Assistant is responsible for.
        answer['results'] = [{**job, 'result': 'unsupported',
                              'message': f"There is no teach-in telegram for {sender_eep} - "
                                         f"teach {sender_id} in at the device itself."}]
        return answer

    try:
        from eltakobus.message import Regular4BSMessage
        from eltakobus.util import AddressExpression

        telegram = Regular4BSMessage(AddressExpression.parse(sender_id)[0], 0x80,
                                     get_teach_in_payload(sender_eep), True)
        target_gateway.send_message(telegram)
    except Exception as e:  # noqa: BLE001 - the answer says what went wrong
        LOGGER.error(f"[{LOG_PREFIX_SENDER_GATEWAY}] Cannot send the teach-in telegram of "
                     f"{sender_id} through {target_gateway.dev_name}: {e}", exc_info=True)
        answer['results'] = [{**job, 'result': 'error', 'message': str(e)}]
        return answer

    LOGGER.info(f"[{LOG_PREFIX_SENDER_GATEWAY}] Teach-in telegram {sender_id} ({sender_eep}) "
                f"sent through '{target_gateway.dev_name}' for {address}.")
    answer['results'] = [{**job, 'result': 'written', 'telegram': str(telegram)}]
    return answer


def _all_gateways(hass: HomeAssistant) -> list:
    from ..core.websocket import get_gateways

    return list(get_gateways(hass))


def _sender_jobs(hass: HomeAssistant, bus_gateway, target_gateway,
                 address: str = None) -> tuple[list[dict], list[dict]]:
    """(jobs, skipped) - the devices of this bus which should get a sender of `target_gateway`.

    Only devices created in the web ui: a device declared in `configuration.yaml` is the
    documented source and is never rewritten from here - it is reported as skipped so the
    answer can say why nothing happened to it.
    """
    from .device_config import get_devices_of_gateway

    entry = _find_gateway_entry(hass, bus_gateway.dev_id)
    ui_devices = get_ui_devices(entry) if entry is not None else {}
    ui_addresses = {str(device.get(CONF_ID, '')).upper()
                    for entries in ui_devices.values() for device in entries or []}

    jobs, skipped = [], []
    for platform, entries in (get_devices_of_gateway(hass, bus_gateway.dev_id) or {}).items():
        for device in entries or []:
            device_address = str(device.get(CONF_ID, '')).upper()
            sender = device.get(CONF_SENDER) or {}
            sender_eep = str(sender.get(CONF_EEP, '') or '')
            if not is_bus_address(device_address) or not sender_eep:
                continue        # a sensor has no sender - there is nothing to switch it with
            if address and device_address != str(address).upper():
                continue
            entry_of = {'platform': str(platform), 'address': device_address,
                        'name': device.get(CONF_NAME),
                        'previous_sender_id': str(sender.get(CONF_ID, '') or ''),
                        'sender_eep': sender_eep,
                        'position': int(device_address.split('-')[3], 16)}
            if device_address not in ui_addresses:
                skipped.append({**entry_of, 'result': 'yaml',
                                'message': "declared in configuration.yaml - change its sender "
                                           "there, it is not rewritten from the web ui."})
                continue
            sender_id = sender_id_for(target_gateway, device_address)
            if sender_id is None:
                skipped.append({**entry_of, 'result': 'out_of_range',
                                'message': f"'{target_gateway.dev_name}' has no address for this "
                                           f"actuator - no base id, or its 128 addresses are used up."})
                continue
            jobs.append({**entry_of, 'sender_id': sender_id})
    return jobs, skipped


async def _async_store_senders(hass: HomeAssistant, bus_gateway, written: list[dict]) -> list[dict]:
    """Write the new sender ids into the stored ui devices - one save for all of them.

    Every write of the options reloads the gateway, so a whole bus must not be saved device by
    device. A device which vanished meanwhile is skipped instead of failing the rest.
    """
    entry = _find_gateway_entry(hass, bus_gateway.dev_id)
    if entry is None:
        return []

    devices = get_ui_devices(entry)
    updated = []
    for job in written:
        stored = next((device for device in devices.get(job['platform'], []) or []
                       if str(device.get(CONF_ID, '')).upper() == job['address']), None)
        if stored is None:
            continue
        sender = dict(stored.get(CONF_SENDER) or {})
        if str(sender.get(CONF_ID, '')).upper() == job['sender_id'].upper():
            continue        # already the configured sender - nothing to save
        sender[CONF_ID] = normalize_address(job['sender_id'])
        sender[CONF_EEP] = job['sender_eep']
        stored[CONF_SENDER] = sender
        updated.append(job)

    if updated:
        await async_save_ui_devices(hass, entry, devices)
        LOGGER.info(f"[{LOG_PREFIX_SENDER_GATEWAY}] Gateway {bus_gateway.dev_id}: "
                    f"{len(updated)} device(s) now send with "
                    + ", ".join(f"{job['address']}->{job['sender_id']}" for job in updated))
    return updated


async def async_assign_sender_gateway(hass: HomeAssistant, bus_gateway, target_gateway,
                                      address: str = None, program: bool = True) -> dict:
    """Give the actuators of one bus the sender addresses of `target_gateway`.

    `address` restricts it to a single device, `program=False` only stores the addresses
    without touching the bus - for an installation whose FAM14 is not connected right now.

    **The bus is only touched where it has to be**: an actuator which already carries the
    address (the memory image of the last scan says so) is switched over in Home Assistant
    alone. A run in which nothing is missing therefore needs no FAM14 and no lock on the bus.

    Returns `{'results': [...], 'updated': [...], 'skipped': [...], 'base_id': ...}`; a device
    whose actuator refused the write keeps its old sender, so it is reported and not changed.
    """
    from ..observation.bus_members import _async_write_teach_in_jobs, sender_is_taught_in

    if not GatewayDeviceType.is_bus_gateway(getattr(bus_gateway, 'dev_type', None)):
        return {'error': 'not_a_bus_gateway',
                'message': f"Gateway {bus_gateway.dev_id} has no RS485 bus."}

    jobs, skipped = _sender_jobs(hass, bus_gateway, target_gateway, address)
    answer = {'gateway_id': bus_gateway.dev_id, 'gateway_name': bus_gateway.dev_name,
              'target_gateway_id': target_gateway.dev_id,
              'target_gateway_name': target_gateway.dev_name,
              'base_id': base_id_of(target_gateway),
              'results': [], 'updated': [], 'skipped': skipped}

    # Only the actuators which do not carry the address yet go onto the bus. Switching back to
    # the bus itself is the case this exists for: the local senders 00-00-B0-xx are in the
    # memories since the search, so nothing has to be written, and demanding a connected FAM14
    # for a change which only rewrites the Home Assistant configuration would be a dead end.
    # An address whose memory was never read counts as missing - sender_is_taught_in() answers
    # None there, and ensure_programmed() checks the device itself again anyway.
    pending, present = [], []
    for job in jobs:
        taught_in = sender_is_taught_in(hass, bus_gateway.dev_id, job['address'],
                                        job['sender_id'])
        (present if taught_in is True else pending).append(job)

    # both checks stand before the "nothing to do" exit: a bus which cannot be written or is
    # occupied has to say so, otherwise a gateway with no devices of its own would answer the
    # same way as a successful run
    if program and pending and not can_program(bus_gateway):
        return {**answer, 'error': 'no_fam14',
                'message': f"'{bus_gateway.dev_name}' cannot write into the actuators - only a "
                           f"FAM14 can. Connect it and try again."}
    if program and pending and bus_gateway.is_bus_busy:
        return {**answer, 'error': 'bus_busy',
                'message': f"The bus is busy with '{bus_gateway.bus_busy_reason}' - try again "
                           f"when it has finished."}
    if not jobs:
        return answer

    if program and pending:
        results = await _async_write_teach_in_jobs(
            hass, bus_gateway, pending,
            f"programming the senders of '{target_gateway.dev_name}'")
    else:
        # nothing was written, so nothing was refused either - every job counts as pending
        results = [{**job, 'result': 'not_programmed'} for job in pending]
    # the actuators which already have the address are part of the result as well: their
    # devices have to be switched over in Home Assistant just like the written ones
    results = results + [{**job, 'result': 'already_taught_in'} for job in present]

    # the write refuses as a whole when somebody else took the bus in between - then nothing
    # was written, and nothing may be stored either
    if results and results[0].get('status') == 'busy':
        return {**answer, 'error': 'bus_busy',
                'message': results[0].get('message', 'The bus is busy.')}

    answer['results'] = results
    # only a device whose actuator really carries the address is switched over: a configured
    # sender which is in no memory is a device which looks fine and does nothing
    taken = [job for job in results
             if job.get('result') in ('written', 'already_taught_in', 'not_programmed')]
    answer['updated'] = await _async_store_senders(hass, bus_gateway, taken)
    return answer


async def async_assign_default_gateway(hass: HomeAssistant, target_gateway,
                                       program: bool = True) -> dict:
    """The same for **every** RS485 bus - "this gateway operates the installation".

    That is the last step of moving an installation off the FAM14: every actuator of every bus
    gets an address of the new gateway and Home Assistant sends with it afterwards.
    """
    from ..core.websocket import get_gateways

    buses = [gateway for gateway in get_gateways(hass)
             if GatewayDeviceType.is_bus_gateway(gateway.dev_type)]
    answer = {'target_gateway_id': target_gateway.dev_id,
              'target_gateway_name': target_gateway.dev_name,
              'base_id': base_id_of(target_gateway), 'buses': []}
    for bus_gateway in buses:
        answer['buses'].append(await async_assign_sender_gateway(
            hass, bus_gateway, target_gateway, program=program))

    answer['updated'] = sum(len(bus.get('updated') or []) for bus in answer['buses'])
    answer['failed'] = sum(1 for bus in answer['buses'] for result in bus.get('results') or []
                           if result.get('result') in ('error', 'unsupported'))
    return answer


### ---------------------------------------------------------------------------
### websocket api
### ---------------------------------------------------------------------------

@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required('type'): WS_DEVICE_SENDER_GATEWAY,
    # the gateway whose addresses the devices should send with
    vol.Required('target_gateway_id'): vol.Coerce(int),
    # the bus to change - left out it is every bus ("this gateway operates the installation")
    vol.Optional('gateway_id'): vol.Coerce(int),
    # one device instead of the whole bus
    vol.Optional('address'): str,
    # False stores the addresses without touching the bus (no FAM14 connected right now)
    vol.Optional('program', default=True): bool,
})
@websocket_api.async_response
async def ws_device_sender_gateway(hass: HomeAssistant, connection, msg) -> None:
    from ..core.websocket import get_gateways

    gateways = get_gateways(hass)
    target = next((g for g in gateways if g.dev_id == msg['target_gateway_id']), None)
    if target is None:
        connection.send_error(msg['id'], 'unknown_gateway',
                              f"No gateway with id {msg['target_gateway_id']}")
        return

    if 'gateway_id' not in msg:
        answer = await async_assign_default_gateway(hass, target, program=msg['program'])
        connection.send_result(msg['id'], answer)
        return

    bus_gateway = next((g for g in gateways if g.dev_id == msg['gateway_id']), None)
    if bus_gateway is None:
        connection.send_error(msg['id'], 'unknown_gateway', f"No gateway with id {msg['gateway_id']}")
        return

    # a wireless actuator has no memory to write into: it learns the address which is sent to
    # it while it is in teach-in mode, so that way in is a telegram instead of a bus write
    if msg.get('address') and not is_bus_address(msg['address']):
        answer = await async_assign_radio_sender(hass, target, msg['address'],
                                                 gateway_id=bus_gateway.dev_id,
                                                 send_teach_in=msg['program'])
    else:
        answer = await async_assign_sender_gateway(hass, bus_gateway, target, msg.get('address'),
                                                   program=msg['program'])
    if answer.get('error'):
        connection.send_error(msg['id'], answer['error'], answer.get('message', ''))
        return
    # one shape for both ways in: the caller always reads `buses`
    connection.send_result(msg['id'], {
        'target_gateway_id': target.dev_id, 'target_gateway_name': target.dev_name,
        'base_id': answer.get('base_id'), 'buses': [answer],
        'updated': len(answer.get('updated') or []),
        'failed': sum(1 for result in answer.get('results') or []
                      if result.get('result') in ('error', 'unsupported')),
    })


def register_websocket_commands(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_device_sender_gateway)
