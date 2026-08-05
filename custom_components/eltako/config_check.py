"""Configuration check: everything which can be verified without sending a single telegram.

The most frequent support case is not a bug of the integration, it is a configuration which
cannot work: a bus address configured for a wireless transceiver, a sender id outside the base
id range of its gateway (the gateway drops those telegrams silently), a sender which was never
taught into the actuator, an EEP which does not match the model that answers at that bus
position. All of that is already known inside the integration - it is just spread over the
configuration, the bus member registry, the memory images and the activity tracker.

This module collects it into one list of findings, each with a severity and a sentence that
says what to do. It sends nothing, locks nothing and can be run at any time; it is offered as
the `config` test of the tests page and reused by the command line.

Severities:
  error   - cannot work like this (wrong address class, unknown gateway, missing sender)
  warning - very probably broken (sender not taught in, never heard from, foreign sender id)
  info    - worth knowing (EEP differs from the model, no travel times, sender shared)
"""

from __future__ import annotations

import logging
from typing import Callable

from homeassistant.const import CONF_DEVICES, CONF_ID, CONF_NAME

from . import config_helpers
from .const import (
    CONF_BASE_ID, CONF_EEP, CONF_GATEWAY, CONF_SENDER, CONF_TIME_CLOSES, CONF_TIME_OPENS,
    DATA_ELTAKO, ELTAKO_CONFIG, GatewayDeviceType)

LOGGER = logging.getLogger("eltako.config_check")

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"
SEVERITIES = (SEVERITY_ERROR, SEVERITY_WARNING, SEVERITY_INFO)

# platforms whose devices are driven by Home Assistant and therefore need a sender
ACTUATOR_PLATFORMS = ("light", "switch", "cover", "climate")


def _finding(severity: str, check: str, message: str, gateway_id=None,
             device: str = None, name: str = None) -> dict:
    return {"severity": severity, "check": check, "message": message,
            "gateway_id": gateway_id, "device": device, "name": name}


def _is_local(address: str) -> bool:
    """A local bus address of a FAM14/FGW14-USB: 00-00-XX-XX."""
    parts = str(address).split("-")
    return len(parts) == 4 and parts[0] == "00" and parts[1] == "00"


def _bus_address(address: str) -> int | None:
    parts = str(address).split("-")
    if not _is_local(address):
        return None
    try:
        return int(parts[3], 16)
    except ValueError:
        return None


def _same_base_id(base_id: str, address: str) -> bool:
    """Is the address inside the base id range of the gateway (first three bytes equal)?"""
    left = str(base_id).split("-")
    right = str(address).split("-")
    if len(left) != 4 or len(right) != 4:
        return False
    return [part.upper() for part in left[:3]] == [part.upper() for part in right[:3]]


def _gateway_type(gateway_config: dict) -> GatewayDeviceType | None:
    from .const import CONF_DEVICE_TYPE
    return GatewayDeviceType.find(str(gateway_config.get(CONF_DEVICE_TYPE, "")))


def get_configuration(hass) -> dict:
    return (getattr(hass, "data", None) or {}).get(DATA_ELTAKO, {}).get(ELTAKO_CONFIG, {}) or {}


def _devices_of_gateway(hass, gateway_config: dict) -> dict:
    """Devices of a gateway from configuration.yaml and from the web ui.

    Reading only the yaml section would let every device created in the web ui pass the check
    unseen - which is exactly the configuration a beginner has.
    """
    yaml_devices = gateway_config.get(CONF_DEVICES, {}) or {}
    if hass is None:
        return yaml_devices
    try:
        from .device_config import get_devices_of_gateway
        return get_devices_of_gateway(hass, gateway_config.get(CONF_ID)) or yaml_devices
    except Exception as e:  # noqa: BLE001 - without config entries the yaml is all there is
        LOGGER.debug(f"Web ui devices are not available: {e}")
        return yaml_devices


def _bus_members_by_address(hass, gateway_id: int) -> dict[int, dict]:
    """Bus positions known for a gateway, keyed by bus address. Empty without a registry."""
    try:
        from .bus_members import get_registry
        registry = get_registry(hass)
        if registry is None:
            return {}
        return {member["bus_address"]: member for member in registry.get_members(hass)
                if member.get("gateway_id") == gateway_id}
    except Exception as e:  # noqa: BLE001 - the check must never fail because of a helper
        LOGGER.debug(f"Bus members are not available: {e}")
        return {}


def _activity(hass, address: str) -> dict | None:
    try:
        from .device_activity import get_activity_tracker
        tracker = get_activity_tracker(hass)
        return tracker.get_activity(address) if tracker else None
    except Exception as e:  # noqa: BLE001
        LOGGER.debug(f"Activity is not available: {e}")
        return None


def check_gateway(gateway_config: dict, devices: dict, hass=None) -> list[dict]:
    """Findings for one gateway and all devices configured for it."""
    gateway_id = gateway_config.get(CONF_ID)
    gateway_type = _gateway_type(gateway_config)
    base_id = str(gateway_config.get(CONF_BASE_ID) or "")
    findings: list[dict] = []

    if gateway_type is None:
        findings.append(_finding(
            SEVERITY_ERROR, "gateway_type",
            f"Unknown device_type '{gateway_config.get('device_type')}'. The integration cannot "
            f"decide how to talk to this gateway.", gateway_id))
        return findings

    is_bus = GatewayDeviceType.is_bus_gateway(gateway_type)
    is_transceiver = GatewayDeviceType.is_transceiver(gateway_type)
    base_id_known = bool(base_id) and base_id.split("-")[0].upper() == "FF"

    if is_transceiver and not base_id_known:
        findings.append(_finding(
            SEVERITY_INFO, "base_id",
            "The base id of this gateway is not in the configuration. It is queried from the "
            "hardware after connecting - sender ids can only be checked once it is known.",
            gateway_id))

    members = _bus_members_by_address(hass, gateway_id) if (hass and is_bus) else {}
    seen_addresses: dict[str, str] = {}
    senders: dict[str, list[str]] = {}

    for platform, entries in (devices or {}).items():
        for entry in entries or []:
            address = str(entry.get(CONF_ID, "")).upper()
            name = entry.get(CONF_NAME) or address
            eep = str(entry.get(CONF_EEP, "") or "")
            sender = entry.get(CONF_SENDER) or {}
            sender_id = str(sender.get(CONF_ID, "") or "").upper()

            def add(severity, check, message):
                findings.append(_finding(severity, check, message, gateway_id, address, name))

            ### address class has to match the gateway
            #
            # A bus gateway hears wireless telegrams as well (the FAM14 is the antenna module of
            # the bus and forwards them), so a wireless *sensor* on a bus gateway is completely
            # normal - only a wireless *actuator* is worth a hint, because the commands of Home
            # Assistant then have to leave the bus by radio, which an FGW14-USB cannot do on its
            # own. A local address on a wireless transceiver on the other hand can never work.
            if is_bus and not _is_local(address) and str(platform) in ACTUATOR_PLATFORMS:
                add(SEVERITY_INFO, "address_class",
                    f"{address} is a wireless address on a bus gateway ({gateway_type.value}). "
                    f"Commands only reach it if a FAM14 transmits them by radio - an FGW14-USB "
                    f"alone has no antenna. For a device on the RS485 bus use 00-00-XX-XX.")
            if is_transceiver and _is_local(address):
                add(SEVERITY_ERROR, "address_class",
                    f"{address} is a local bus address, but this gateway "
                    f"({gateway_type.value}) is a wireless transceiver and expects "
                    f"FF-XX-XX-XX. Configure the device for the bus gateway instead.")

            ### duplicates
            if address in seen_addresses:
                add(SEVERITY_ERROR, "duplicate_device",
                    f"{address} is configured twice for this gateway (as "
                    f"{seen_addresses[address]} and as {platform}). The second entry is dropped.")
            else:
                seen_addresses[address] = str(platform)

            ### sender
            if str(platform) in ACTUATOR_PLATFORMS:
                if not sender_id:
                    add(SEVERITY_ERROR, "sender_missing",
                        f"No sender configured. Home Assistant needs an own sender address to "
                        f"send commands to {address}.")
                else:
                    senders.setdefault(sender_id, []).append(address)
                    if is_transceiver and base_id_known and not _same_base_id(base_id, sender_id):
                        add(SEVERITY_WARNING, "sender_base_id",
                            f"Sender {sender_id} is outside the base id range of this gateway "
                            f"({base_id.rsplit('-', 1)[0]}-XX). A transceiver only transmits "
                            f"telegrams of its own range, so the command never reaches the air.")
                    if is_bus and not _is_local(sender_id):
                        add(SEVERITY_WARNING, "sender_base_id",
                            f"Sender {sender_id} is not a local address. On the RS485 bus the "
                            f"senders of Home Assistant are addresses like 00-00-B0-XX.")

            ### what the bus told us about that position
            position = _bus_address(address)
            member = members.get(position) if position is not None else None
            if members and member is None and is_bus:
                add(SEVERITY_WARNING, "not_on_the_bus",
                    f"Position {position} never answered on the bus. Either the actuator is not "
                    f"there, or it sits on another bus/gateway.")
            elif member:
                configured_eep = eep.upper()
                suggested = str(member.get("suggested_eep") or "").upper()
                if suggested and configured_eep and suggested != configured_eep:
                    add(SEVERITY_INFO, "eep_differs",
                        f"Configured as {configured_eep}, but position {position} answers as "
                        f"{member.get('device_class') or 'unknown model'}, for which "
                        f"{suggested} is the usual profile.")
                taught_in = member.get("taught_in")
                if sender_id and taught_in is not None and member.get("scanned_at"):
                    known = {str(sensor.get("sensor_id", "")).upper() for sensor in taught_in}
                    if known and sender_id not in known:
                        add(SEVERITY_WARNING, "sender_not_taught_in",
                            f"Sender {sender_id} is not in the memory of the actuator "
                            f"(read at {member.get('scanned_at')}). Teach it in with "
                            f"'check & teach in HA senders' or with PCT14.")

            ### has it ever been heard from?
            if hass is not None:
                activity = _activity(hass, address)
                if activity is not None and not activity.get("count"):
                    add(SEVERITY_WARNING, "never_heard_of",
                        f"No telegram of {address} was ever recorded. Wrong address, wrong "
                        f"gateway, or the device does not report by itself.")

            ### platform specific
            if str(platform) == "cover" and not (entry.get(CONF_TIME_CLOSES) and entry.get(CONF_TIME_OPENS)):
                add(SEVERITY_INFO, "cover_times",
                    "Without time_closes and time_opens the cover can only be opened and "
                    "closed completely - no position, no tilt. The cover travel time test "
                    "measures the values.")

    for sender_id, addresses in senders.items():
        if len(addresses) > 1:
            findings.append(_finding(
                SEVERITY_INFO, "sender_shared",
                f"Sender {sender_id} is used by {len(addresses)} devices "
                f"({', '.join(addresses[:5])}{' ...' if len(addresses) > 5 else ''}). That is "
                f"intended for a group, but a command then always reaches all of them.",
                gateway_id))

    return findings


def check_configuration(hass, gateway_ids: list[int] | None = None) -> dict:
    """Check the whole configuration (or only the given gateways)."""
    config = get_configuration(hass)
    gateways = config.get(CONF_GATEWAY, []) or []
    if gateway_ids:
        wanted = {int(gateway_id) for gateway_id in gateway_ids}
        gateways = [gateway for gateway in gateways if gateway.get(CONF_ID) in wanted]

    findings: list[dict] = []
    device_count = 0
    for gateway_config in gateways:
        devices = _devices_of_gateway(hass, gateway_config)
        device_count += sum(len(entries or []) for entries in devices.values())
        findings.extend(check_gateway(gateway_config, devices, hass))

    if not gateways:
        findings.append(_finding(SEVERITY_WARNING, "no_gateway",
                                 "No gateway is configured, so there is nothing to check."))

    counts = {severity: len([f for f in findings if f["severity"] == severity])
              for severity in SEVERITIES}
    return {
        "test": "config",
        "success": counts[SEVERITY_ERROR] == 0 and counts[SEVERITY_WARNING] == 0,
        "findings": findings,
        "counts": counts,
        "gateway_count": len(gateways),
        "device_count": device_count,
    }


async def run_config_test(hass, params: dict, log: Callable[[str, str], None],
                          stop_event=None) -> dict:
    """Runner of the `config` test - the only one which sends nothing.

    `log_findings` is False for the command line: it prints the findings itself (sorted and
    filtered by severity), so the log would only duplicate them.
    """
    gateway_ids = params.get("gateways") or None
    if isinstance(gateway_ids, (int, str)):
        gateway_ids = [gateway_ids]

    log("Checking the configuration - no telegram is sent.", "info")
    result = check_configuration(hass, gateway_ids)

    log(f"{result['device_count']} device(s) of {result['gateway_count']} gateway(s) checked.", "info")
    styles = {SEVERITY_ERROR: "error", SEVERITY_WARNING: "error", SEVERITY_INFO: "info"}
    if params.get("log_findings", True):
        for finding in result["findings"]:
            where = " ".join(part for part in [
                f"[gateway {finding['gateway_id']}]" if finding["gateway_id"] is not None else "",
                f"{finding['name']} ({finding['device']}):" if finding["device"] else "",
            ] if part)
            log(f"{finding['severity'].upper()} {where} {finding['message']}".strip(),
                styles.get(finding["severity"], "info"))

    counts = result["counts"]
    log(f"RESULT: {counts[SEVERITY_ERROR]} error(s), {counts[SEVERITY_WARNING]} warning(s), "
        f"{counts[SEVERITY_INFO]} hint(s).", "ok" if result["success"] else "error")
    return result
