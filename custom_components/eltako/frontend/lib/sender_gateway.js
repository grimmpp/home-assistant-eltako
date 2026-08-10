/**
 * Which gateway switches an actuator - shared by the device table (expert) and the setup
 * instruction of the simple view.
 *
 * An RS485 actuator only reacts to the sender addresses in its own memory, and a transceiver
 * only transmits senders out of its own base id range. Both halves have to agree, so picking
 * a gateway for a device does two things at once (backend: config/sender_gateway.py):
 *
 *   1. `base id of that gateway + the last byte of the actuator address` is written into the
 *      actuator - which only a FAM14 can do, so it has to be connected,
 *   2. and the same address becomes the **sender** of that device in Home Assistant.
 *
 * The bus itself is the default: there the local senders `00-00-B0-xx` apply, the addresses
 * the FAM14 works with and which the detection and the yaml import hand out.
 */

import { WS } from "./api.js";
import { escapeHtml, icon } from "./utils.js";

/** the picker of renderSenderPicker() - both pages which show it include these */
export const SENDER_PICKER_STYLES = `
  .sender-picker { display: flex; flex-wrap: wrap; align-items: center; gap: 6px;
                   font-size: .72rem; color: var(--eltako-muted); }
  .sender-picker label { display: inline-flex; align-items: center; gap: 4px; min-width: 0; }
  /* The name of a gateway is what is read here, so the box is as wide as it needs to be and
     cuts the rest off instead of showing an address which nobody compares by eye - the base
     id stands in the tooltip of the option. A select which is 150px wide showed
     "FAM-USB (FF-C0-0..." and neither of the two things it says. */
  .sender-picker select { font-size: .72rem; min-width: 90px; max-width: 100%;
                          text-overflow: ellipsis; }
  .sender-picker select[disabled] { opacity: .5; }
  .sender-picker ha-icon, .sender-picker .glyph { --mdc-icon-size: 14px; }
`;

/** gateway types which sit on an RS485 bus - they have no base id range of their own to hand out */
export const BUS_GATEWAY_TYPES = ["fam14", "fgw14usb", "ftd14"];

export function isBusGatewayType(type) {
  return BUS_GATEWAY_TYPES.includes(String(type));
}

/** the gateways which can carry an installation by radio: everything with a base id off the bus */
export function senderTargets(gateways) {
  return (gateways || []).filter((gateway) => !isBusGatewayType(gateway.type) && gateway.base_id);
}

/**
 * Every gateway the whole installation can be operated with - the choice of the setup guide.
 *
 * Wider than senderTargets() on purpose: the gateways **on the bus** belong in that list as
 * well. Moving an installation back onto the FAM14 (or onto an FGW14-USB) changes the sender
 * addresses in Home Assistant just as much as moving it to a wireless gateway - there the
 * local `00-00-B0-xx` apply - and that half has to be done in either direction. What is
 * written into the actuators is a different question: an address which is already in their
 * memory is not written again (backend: config/sender_gateway.py).
 *
 * A wireless gateway which never reported a base id stays out: it has no addresses to give.
 */
export function defaultGatewayChoices(gateways) {
  return (gateways || []).filter((gateway) => isBusGatewayType(gateway.type) || gateway.base_id);
}

/**
 * One gateway as an `<option>`: **the name, and nothing else in the line.**
 *
 * The base id used to stand next to it, which made every entry twice as long as the box - a
 * dropdown reading "FAM-USB (FF-C0-0..." says neither which gateway it is nor which addresses
 * it hands out. The name is what is picked by, so the address moves into the tooltip, where it
 * can be read when it is wanted. The bus keeps a short "· bus": it is the one entry which
 * means something different (the local senders `00-00-B0-xx` instead of a base id range).
 */
export function gatewayOption(gateway, { selected = false } = {}) {
  const bus = isBusGatewayType(gateway.type);
  return `<option value="${escapeHtml(gateway.id)}" ${selected ? "selected" : ""}
    title="${escapeHtml(bus
      ? `${gateway.name} - the RS485 bus itself: the local sender addresses 00-00-B0-xx`
      : `${gateway.name} - base id ${gateway.base_id}`)}"
    >${escapeHtml(gateway.name)}${bus ? " · bus" : ""}</option>`;
}

/**
 * Which gateway a configured sender address belongs to - the current choice of a device.
 *
 * A local sender (`00-00-…`) is the bus itself, everything else belongs to the gateway whose
 * base id range it lies in. Undefined when no configured gateway owns it: an address which was
 * imported from somewhere else, or a gateway which has been removed since.
 */
export function senderGatewayOf(gateways, gatewayId, senderId) {
  const sender = String(senderId || "").toUpperCase();
  if (!sender) return undefined;
  if (sender.startsWith("00-00-")) {
    return (gateways || []).find((gateway) => String(gateway.id) === String(gatewayId));
  }
  return (gateways || []).find((gateway) => gateway.base_id
    && String(gateway.base_id).toUpperCase().slice(0, 8) === sender.slice(0, 8));
}

/**
 * The picker of one device: which gateway switches it.
 *
 * The two kinds of actuator need two different ways in, which is why this is not one control:
 *
 * * a **bus actuator** carries the address in its memory. It is written over the bus - only a
 *   FAM14 can do that - and which address it is follows from the bus position, so picking the
 *   gateway is the whole interaction.
 * * a **wireless actuator** has no memory anybody can write into. It learns the address which
 *   is sent to it while it is in teach-in mode, so the picker is followed by a **teach in**
 *   button: the device is put into learn mode and then the telegram goes out.
 *
 * Both store the chosen address as the sender of the device in Home Assistant - otherwise the
 * integration would keep transmitting the old one.
 *
 * Returns "" where the choice would be a lie: a device out of `configuration.yaml` (it is
 * changed there), a sensor (nothing switches it), or an installation without any gateway which
 * could take it over.
 */
export function renderSenderPicker(device, gateways, { label = "Switched by" } = {}) {
  if (!device.editable || !device.sender || !device.sender.eep) return "";

  const onBus = String(device.address || "").toUpperCase().startsWith("00-00-00-");
  const bus = (gateways || []).find((gateway) => String(gateway.id) === String(device.gateway_id));
  const targets = senderTargets(gateways);
  if (!targets.length && !(onBus && bus)) return "";

  const current = senderGatewayOf(gateways, device.gateway_id, device.sender.id);
  const choices = (onBus && bus ? [bus] : []).concat(targets);
  const options = choices.map((gateway) =>
    gatewayOption(gateway, { selected: !!current && current.id === gateway.id })).join("");

  return `
    <div class="sender-picker">
      <label>${icon("mdi:router-wireless", "((‧))")} ${escapeHtml(label)}
        <select data-sender-gateway="${escapeHtml(device.address)}|${escapeHtml(device.gateway_id)}|${onBus ? "bus" : "radio"}"
          title="${onBus
            ? "Which gateway switches this actuator. Its address is written into the actuator and Home Assistant sends with it - only a FAM14 can write, so it has to be connected."
            : "Which gateway switches this actuator. A wireless device learns the address from a telegram, so pick the gateway and press 'teach in' while the device is in learn mode."}">
          ${current ? "" : `<option value="" selected>own address</option>`}
          ${options}
        </select>
      </label>
      ${onBus ? "" : `<button class="action small" data-sender-teach-in="${escapeHtml(device.address)}"
          title="Put the device into teach-in mode, then press this: the address of the chosen gateway is sent to it and stored as the sender of this device.">teach in</button>`}
    </div>`;
}

/**
 * The listeners of every picker in `root`. `reload` is called after a change went through.
 *
 * A bus actuator is written as soon as its gateway is picked; a wireless one waits for its
 * button, because its telegram is only useful while the device is in learn mode.
 */
export function bindSenderPickers(ctx, root, reload) {
  const run = async (select, element, question) => {
    const [address, gatewayId] = select.dataset.senderGateway.split("|");
    if (!select.value) {
      alert("Pick the gateway which should switch this device first.");
      return;
    }
    const name = select.options[select.selectedIndex].textContent.trim();
    if (!confirm(question(name))) return false;
    element.disabled = true;
    const result = await assignSenderGateway(ctx, {
      targetGatewayId: select.value, gatewayId, address,
    });
    element.disabled = false;
    if (!result) {
      alert((ctx.api.lastError || {}).message || "The gateway could not be changed.");
      ctx.api.lastError = null;
      return false;
    }
    alert(describeAssignResult(result));
    await reload();
    return true;
  };

  root.querySelectorAll("select[data-sender-gateway]").forEach((select) => {
    const previous = select.value;
    select.addEventListener("change", async () => {
      // a wireless device is taught in with its button - picking alone sends nothing
      if (select.dataset.senderGateway.split("|")[2] !== "bus") return;
      const done = await run(select, select, (name) =>
        `Let "${name}" switch this device?\n\n`
        + "Its address is written into the actuator and Home Assistant sends with it "
        + "afterwards. Nothing is removed - what switched the device before keeps switching "
        + "it. Only a FAM14 can write, so it has to be connected; the bus is locked for a "
        + "moment.");
      if (!done) select.value = previous;
    });
  });

  root.querySelectorAll("button[data-sender-teach-in]").forEach((button) => {
    button.addEventListener("click", async () => {
      const select = button.closest(".sender-picker")?.querySelector("select");
      if (!select) return;
      await run(select, button, (name) =>
        `Teach this device in on "${name}"?\n\n`
        + "Put the device into teach-in mode now - the teach-in telegram is sent through that "
        + "gateway and its address is stored as the sender of this device. A device which is "
        + "not in teach-in mode ignores the telegram, so it can simply be repeated.");
    });
  });
}

/**
 * Ask the backend to move devices onto the senders of one gateway.
 *
 * `params` is `{ targetGatewayId, gatewayId?, address? }` - without a gateway id it is every
 * bus of the installation ("this gateway operates everything from now on"). Returns the
 * answer of the backend, or null when it refused - `ctx.api.lastError` says why.
 */
export async function assignSenderGateway(ctx, { targetGatewayId, gatewayId, address }) {
  const message = { target_gateway_id: Number(targetGatewayId) };
  if (gatewayId !== undefined && gatewayId !== null) message.gateway_id = Number(gatewayId);
  if (address) message.address = address;
  return ctx.api.call(WS.DEVICE_SENDER_GATEWAY, message);
}

/**
 * The result in plain words: what was written, what Home Assistant sends with now, and what
 * did not work. A device which refused the write keeps its old sender - which is exactly the
 * thing somebody has to be told, so it is named instead of counted.
 */
export function describeAssignResult(result) {
  if (!result) return "Nothing was changed.";
  const buses = result.buses || [];
  const results = buses.flatMap((bus) => bus.results || []);
  const updated = buses.flatMap((bus) => bus.updated || []);
  const skipped = buses.flatMap((bus) => bus.skipped || []);
  const failed = results.filter((entry) => ["error", "unsupported"].includes(entry.result));
  const busErrors = buses.filter((bus) => bus.error);

  const lines = [`${result.target_gateway_name}${result.base_id ? ` (${result.base_id})` : ""}:`];
  lines.push(`${updated.length} device${updated.length === 1 ? "" : "s"} now send${
    updated.length === 1 ? "s" : ""} with an address of this gateway`
    + (results.length ? `, ${results.length - failed.length}/${results.length} actuator${
      results.length === 1 ? "" : "s"} took it.` : "."));
  if (updated.length) {
    lines.push("", ...updated.map((entry) =>
      `${entry.address}  ${entry.previous_sender_id || "-"}  ->  ${entry.sender_id}`));
  }
  if (failed.length) {
    lines.push("", "Not written (these keep their old sender):",
      ...failed.map((entry) => `${entry.address}  ${entry.message || entry.result}`));
  }
  if (skipped.length) {
    lines.push("", "Left alone:",
      ...skipped.map((entry) => `${entry.address}  ${entry.message || entry.result}`));
  }
  if (busErrors.length) {
    lines.push("", ...busErrors.map((bus) => `${bus.gateway_name}: ${bus.message || bus.error}`));
  }
  return lines.join("\n");
}
