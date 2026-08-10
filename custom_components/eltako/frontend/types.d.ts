/**
 * Types of the web ui. Development aid only - nothing here is loaded at runtime, the panel
 * stays plain javascript without a build step (see eltako-panel.js).
 *
 * The payload types are derived from the python backend; every block names the function
 * which produces it. When a websocket handler changes its response, change the type here
 * as well - `npx tsc -p custom_components/eltako/frontend` then shows every page which
 * still reads the old field.
 *
 * Types marked "partial" carry an index signature: their known fields are checked, unknown
 * ones are allowed, because the response is assembled dynamically in the backend.
 */

/* --------------------------------------------------------------- home assistant */

export interface HassEntityState {
  entity_id: string;
  state: string;
  attributes: { unit_of_measurement?: string; friendly_name?: string; [key: string]: any };
  last_changed?: string;
  last_updated?: string;
}

/** The parts of the home assistant connection the panel uses (lib/api.js). */
export interface HassConnection {
  sendMessagePromise<T = any>(message: { type: string; [key: string]: any }): Promise<T>;
  subscribeMessage<T = any>(
    callback: (message: T) => void,
    subscription: { type: string; [key: string]: any },
  ): Promise<() => void>;
}

/** The `hass` object home assistant sets on the panel element. Only what the ui reads. */
export interface HomeAssistant {
  connection: HassConnection;
  states: Record<string, HassEntityState>;
  callService(domain: string, service: string, data?: Record<string, any>): Promise<any>;
  language?: string;
  user?: { name?: string; is_admin?: boolean };
}

declare global {
  interface Window {
    /** set by the shell of the eltako_standalone runtime - absent inside home assistant */
    eltakoStandalone?: boolean;
    /** the home assistant frontend publishes its websocket connection here */
    hassConnection?: Promise<{ conn: HassConnection }>;
  }
}

/** A custom element of the home assistant frontend (e.g. ha-menu-button). */
export type HaElement = HTMLElement & { hass?: HomeAssistant; narrow?: boolean };

/* ------------------------------------------------------- panel: state and pages */

export type PanelMode = "user" | "expert";

/** Data shared between all pages, see the constructor of EltakoPanel. */
export interface PanelState {
  integrationInfo: IntegrationInfo | null;
  logInfo: LogInfo | null;
  statistics: StatisticsResult | null;
  telegrams: TelegramRecord[];

  paused: boolean;
  telegramFilter: string;
  directionFilter: string;
  gatewayFilter: string;
  onlyUnknown: boolean;
  deviceFilter: string;
  onlyUnknownDevices: boolean;

  /** pages/radio.js: one telegram as every gateway received it */
  radioComparison: RadioComparisonReport | null;
  radioFilter: string;
  /** how far apart two receptions may be to count as the same transmission */
  radioWindowMs: number;
  /** which telegrams the list shows - a key of RadioComparisonReport.summary.filters */
  radioView: string;
  /** the direct comparison: only these gateways take part in the analysis (empty = all) */
  radioGateways: Array<string | number>;
  /** only the telegrams of this sender (null = all) */
  radioSender: string | null;
  /** which burst details are unfolded, keyed by '<address>|<timestamp_ms>' */
  radioOpen: Record<string, boolean>;

  deviceForm: DeviceFormDescriptor | null;
  configuredDevices: ConfiguredDevice[];
  configFilter: string;
  configSort: string;
  deviceView: string;
  /** which device the details popup of the expert page shows: 'platform|address|gateway id' */
  deviceDetails?: string | null;
  configSortDescending: boolean;
  onlySilent: boolean;

  simpleFilter: string;
  simpleEditor: any;
  /** the popup of the simple view: {kind: 'device' | 'gateway', key} - see pages/home.js */
  simpleDetails?: { kind: string; key: string } | null;

  settingsForm: SettingsFormDescriptor | null;
  settingsError: string | null;
  settingsMessage: string | null;

  helpCatalog: any;
  helpFilter: string;

  portScan: any;
  busMembers: BusMembersResult | null;
  gatewayForm: GatewayFormDescriptor | null;
  gatewayEditor: any;
  plugAndPlay: PlugAndPlayStatus | null;
  gatewayError: string | null;
  gatewayMessage: string | null;
  portScanRunning: boolean;
  editor: any;
  pendingNewDevice: any;
  pendingNewGateway: any;
  deviceSort: string;
  deviceSortDescending: boolean;

  /**
   * View state which the pages create on demand - it is not in the initializer of the
   * constructor, so these keys are undefined until the page ran once.
   */
  /** the address whose "what is this?" popup is open (live telegrams and statistics) */
  unknownDetails?: string | null;

  /** pages/reception.js: the site survey */
  reception?: ReceptionSurvey | null;
  receptionWindow?: number;
  receptionAddress?: string | null;
  receptionSpots?: any[];
  /** pages/telegrams.js: the free send form */
  sendForm?: any;
  sendFormDescriptor?: { gateways: Gateway[]; eeps: EepDescriptor[] } | null;

  /** pages/control.js */
  controlEntities?: any;
  controlFilter?: string;
  controlSendNotes?: any;
  controlSendOpen?: any;
  controlSendValues?: any;
  /** start values of the type bar; the buttons themselves write into controlTypes */
  controlShowSensors?: boolean;
  controlShowTeachInButtons?: boolean;
  /** which kinds of entity the type bar shows: platform (or "teach_in") -> on */
  controlTypes?: Record<string, boolean>;
  telegramForm?: any;

  /** pages/tests.js */
  deviceTests?: any;
  dtActuatorCommand?: any;
  dtActuatorGateway?: any;
  dtConfigGateway?: any;
  dtCoverAddresses?: any;
  dtCoverGateway?: any;
  dtCoverSenders?: any;
  dtCoverSequence?: any;

  /** pages/devices_config.js: the memory content of a bus device, shown in the drawer */
  memoryPanel?: any;

  /** pages/simulation.js */
  simulation?: any;
  simulationBusy?: boolean;
  simulationError?: string | null;
  simulationFocusForm?: any;
  simulationMessage?: string | null;
  simulationNewDevice?: any;
  simulationNewGateway?: any;
  simulationNotes?: any;
  simulationTeachIn?: any;
  simulationUnavailable?: any;
  /** what the integration is busy with right now - polled by the shell, see lib/activity.js */
  activity?: Activity;
}

/** What the shell hands to every page hook (EltakoPanel._context). */
export interface PageContext {
  hass: HomeAssistant;
  api: import("./lib/api.js").EltakoApi;
  state: PanelState;
  root: ShadowRoot;
  /** live entity states: register the ids an element shows, patch it when they change */
  entities: import("./lib/entity_hub.js").EntityHub;
  mode: PanelMode;
  setMode(mode: PanelMode, pageId?: string | null): void;
  loadIntegrationInfo(): Promise<IntegrationInfo | null>;
  /** just started something long: show it in the banner of the panel right away */
  refreshActivity(): Promise<void>;
  /** may this be started now? token as in `data-busy-block` - see lib/activity.js */
  isBusy(token?: string): boolean;
  busyReason(token?: string): string | null;
  loadLogInfo(): Promise<LogInfo | null>;
  loadStatistics(): Promise<StatisticsResult | null>;
  loadRecentTelegrams(): Promise<TelegramRecord[]>;
  navigate(pageId: string): void;
  requestRender(): void;
  requestContentRender(immediately?: boolean): void;
  renderRecordingDisabled(): string;
}

/**
 * The contract of a page module (`export const page = {...}` in pages/).
 * Only `id`, `title` and `render` are mandatory - everything else is a hook the shell
 * calls when it is present.
 */
export interface Page {
  id: string;
  title: string;
  render(ctx: PageContext): string;

  subtitle?: string;
  icon?: string;
  glyph?: string;
  styles?: string;
  /** in which views the page appears (PanelMode values); without it: expert only */
  modes?: string[];
  /** the page needs the eltako_standalone runtime and is hidden inside home assistant */
  standaloneOnly?: boolean;
  /** the page is empty without telegram recording - the shell hides its toolbar then */
  needsRecording?: boolean;
  /** periodic reload interval in milliseconds */
  refreshMs?: number;

  visible?(ctx: PageContext): boolean;
  badge?(ctx: PageContext): string | null;
  load?(ctx: PageContext): void | Promise<void>;
  isEditing?(ctx: PageContext): boolean;
  renderStatus?(ctx: PageContext): string;
  renderToolbar?(ctx: PageContext): string;
  bindToolbar?(ctx: PageContext, root: ShadowRoot): void;
  afterRender?(ctx: PageContext, root: ShadowRoot): void;
  onTelegram?(ctx: PageContext, telegram: TelegramRecord): void;
  /** the page is closed: drop listeners and timers which would outlive its dom */
  leave?(ctx: PageContext): void;

  /**
   * Pages keep their own helpers and state on the page object (`this._renderFeatures`,
   * `this._unsubscribe`, ...). The hooks above are still checked - only names which are
   * not part of the contract fall back to `any`.
   */
  [key: string]: any;
}

/* ------------------------------------------- core/websocket.py: gateways and info */

/** _get_configured_gateways() */
export interface Gateway {
  name: string;
  id: number;
  type: string;
  config_entry_id: string;
  unique_id: string;
  baud_rate: number;
  serial_path: string;
  base_id: string;
  model: string | null;
  auto_reconnect: boolean;
  message_delay: number | null;
  native_protocol: string | null;
  /** null when the connection state cannot be read */
  connected: boolean | null;
  ha_device_id: string | null;
  /** a gateway without hardware - its devices are simulated in this process */
  simulated: boolean;
}

/** _get_entity_summary() */
export interface EntitySummary {
  entity_count: number;
  device_count: number;
  count_by_platform: Record<string, number>;
  areas: string[];
}

/** ws_integration_info() */
export interface IntegrationInfo {
  domain: string;
  name: string;
  version: string | null;
  documentation: string | null;
  issue_tracker: string | null;
  codeowners: string[];
  iot_class: string | null;
  requirements: string[];
  home_assistant_version: string;
  general_settings: Record<string, any>;
  telegram_logging_enabled: boolean;
  gateways: Gateway[];
  entities: EntitySummary;
}

/** get_eep_descriptors() - the send forms are built from this */
export interface EepDescriptor {
  eep: string;
  fields: string[];
  defaults: Record<string, any>;
  /** what the values mean: named options, units, ranges (simulation/core.describe_fields) */
  field_info: Record<string, any>;
  conditional: Record<string, any>;
  /** false for decode-only profiles - no send form is offered for those */
  sendable: boolean;
  description: string | null;
}

/* ------------------------------- observation/enocean_logger.py: telegrams and log */

/**
 * One recorded telegram (EnOceanTelegramLogger._build_record). The fields below `area` are
 * only present when the telegram carries them.
 */
export interface TelegramRecord {
  seq: number;
  /** iso timestamp with microseconds */
  timestamp: string;
  timestamp_ms: number;
  direction: string;
  gateway_id: number | null;
  gateway_name: string | null;
  gateway_type: string | null;
  /** produced by the simulation instead of received from real hardware */
  simulated: boolean;
  protocol: string | null;
  msg_type: string;
  address: string | null;
  local_address: string | null;
  known: boolean;
  role: string | null;
  eep: string | null;
  device_name: string | null;
  entity_ids: string[];
  platforms: string[];
  area: string | null;

  org?: string | null;
  /** only esp3 transceivers report the signal strength */
  rssi_dbm?: number;
  status?: string;
  data?: string;
  payload?: string;
  is_request?: boolean;
  rp_count?: number;
  t21?: any;
  nu?: any;
  repeated?: boolean;
  raw?: string | null;
  teach_in_profile?: string;
  teach_in_manufacturer?: any;
  /** position on the rs485 bus - bus messages have no enocean address */
  bus_address?: number;
  reported_address?: any;
  reported_size?: any;
  memory_size?: any;
  model?: any;
  is_fam?: any;
  row?: any;
}

/**
 * EnOceanTelegramLogger.get_info(), or _disabled_response() when recording is off - then
 * only `enabled: false` and `hint` are set, which is why everything else is optional.
 */
export interface LogInfo {
  enabled: boolean;
  /** how to switch recording on - only present while it is off */
  hint?: string;

  started_at?: string;
  file_logging_enabled?: boolean;
  file_path?: string | null;
  file_format?: string;
  file_written_count?: number;
  file_dropped_count?: number;
  file_error?: string | null;
  file_rotate_after_days?: number | null;
  file_max_size_mb?: number | null;
  file_backup_count?: number | null;
  file_oldest_record_at?: string | null;
  timeseries_enabled?: boolean;
  timeseries?: TimeseriesStatus | null;
  grafana_url?: string;
  buffer_size?: number;
  buffered_count?: number;
  include_polling?: boolean;
  decode_eep?: boolean;
  total_count?: number;
  filtered_count?: number;
  error_count?: number;
  decode_error_count?: number;
  telegrams_per_minute?: number;
  known_address_count?: number;
  log_levels?: Record<string, string>;
}

/** observation/timeseries.py: InfluxExporter.get_status() */
export interface TimeseriesStatus {
  url: string;
  bucket: string;
  measurement: string;
  exported_count: number;
  dropped_count: number;
  failed_count: number;
  batch_count: number;
  queued_count: number;
  last_error: string | null;
  last_export_at: string | null;
}

/** DeviceStatistics.to_dict() - one row of the statistics page */
export interface DeviceStatistics {
  address: string;
  local_address: string | null;
  known: boolean;
  role: string | null;
  name: string | null;
  eep: string | null;
  area: string | null;
  entity_ids: string[];
  platforms: string[];
  gateway_ids: number[];
  count: number;
  count_incoming: number;
  count_outgoing: number;
  msg_types: Record<string, number>;
  teach_in_count: number;
  teach_in_profile: string | null;
  first_seen: string | null;
  last_seen: string | null;
  last_data: string | null;
  last_status: string | null;
  last_decoded: any;
  min_interval: number | null;
  max_interval: number | null;
  avg_interval: number | null;
  /** added by telegram_suggestions.enrich_unknown() for unknown addresses only */
  suggestions?: any;
}

/** the summary of get_statistics(): get_info() plus the counters below */
export interface StatisticsSummary extends LogInfo {
  device_count?: number;
  known_device_count?: number;
  unknown_device_count?: number;
  bus_message_count?: number;
  count_by_gateway?: Record<string, number>;
  count_by_msg_type?: Record<string, number>;
}

/** EnOceanTelegramLogger.get_statistics() */
export interface StatisticsResult {
  summary: StatisticsSummary;
  devices: DeviceStatistics[];
  /** filtered, sorted and enriched - ready to render */
  unknown_devices: DeviceStatistics[];
}

/* ---------------------------------------------------- config/: devices and forms */

/** one entry of _describe_devices() */
export interface ConfiguredDevice {
  gateway_id: number;
  gateway_name: string;
  gateway_set_up: boolean;
  simulated: boolean;
  config_entry_id: string | null;
  platform: string;
  /** 'yaml' devices come from configuration.yaml and cannot be edited here */
  source: "yaml" | "ui";
  editable: boolean;
  address: string;
  external_address: string | null;
  activity: DeviceActivity | null;
  sender_activity: DeviceActivity | null;
  ha_device_id: string | null;
  entity_ids: string[];
  name: string | null;
  eep: string | null;
  area: string | null;
  sender: { id?: string; eep?: string; [key: string]: any } | null;
  /** null when it cannot be told (no bus device, or its memory was never read) */
  sender_taught_in: boolean | null;
  config: Record<string, any>;
}

/** observation/device_activity.py - partial */
export interface DeviceActivity {
  last_seen?: string;
  count?: number;
  [key: string]: any;
}

/** One input of a form, rendered by lib/form.js. Derived from the voluptuous schemas. */
export interface FormField {
  name: string;
  label: string;
  type: "text" | "address" | "select" | "combo" | "boolean" | "number" | "int_list" | "group";
  required?: boolean;
  /** shown but not editable here (e.g. a setting locked by configuration.yaml) */
  disabled?: boolean;
  help?: string;
  /** select/combo: a plain value or {value, label} */
  options?: Array<string | { value: string; label?: string }>;
  min?: number;
  max?: number;
  /** type 'group' only: the fields of the nested object */
  fields?: FormField[];
  [key: string]: any;
}

/** ws_device_form() - partial, the platform blocks come from the schemas */
export interface DeviceFormDescriptor {
  platforms: Array<{ name?: string; label?: string; fields: FormField[]; [key: string]: any }>;
  areas: string[];
  gateways: Array<{
    id: number | null;
    name: string;
    base_id: string;
    config_entry_id: string;
  }>;
  [key: string]: any;
}

/** ws_gateway_form() - partial */
export interface GatewayFormDescriptor {
  ports: Array<{
    device: string;
    name: string | null;
    free: boolean;
    by_id: string | null;
    suggested_device_types: string[];
    /** id of the EnOcean transceiver - only known once the port was opened, see gateway_identity.py */
    chip_id: string | null;
    base_id: string | null;
    /** the ids above are what the stick answered earlier, not what it says right now */
    ids_remembered: boolean;
  }>;
  default_base_id: string;
  editable_fields: string[];
  hint: string;
  fields?: FormField[];
  [key: string]: any;
}

/** general_settings.get_form_descriptor() - partial */
export interface SettingsFormDescriptor {
  settings: Array<{
    name: string;
    value: any;
    /** where the effective value comes from */
    origin: "ui" | "yaml" | "default";
    fallback: any;
    extra_help?: string | null;
    [key: string]: any;
  }>;
  [key: string]: any;
}

/* ---------------------------------------------------------- observation/tools */

/** ws_bus_members() */
export interface BusMembersResult {
  members: any[];
  scans_running: Record<string, boolean>;
  busy_with: any;
  /** progress per running scan, keyed by gateway id */
  scan_progress: Record<string, any>;
  hint: string;
}

/** tools/plug_and_play.get_status() */
export interface PlugAndPlayStatus {
  enabled: boolean;
  interval: number;
  periodic: boolean;
  running: boolean;
  step: string | null;
  stage: string | null;
  stages: string[];
  bus_scans: any[];
  started_at: string | null;
  last_run: string | null;
  last_report: any;
  setting: string;
  hint: string;
}

/**
 * One thing the integration is busy with right now (core/websocket.get_activity). The web ui
 * polls this on every page and shows it as a banner, so a user can tell a long operation from
 * a broken one - see `_renderActivity` in eltako-panel.js.
 */
export interface ActivityJob {
  /** 'detection' = a plug & play run, 'bus' = an operation which has the bus of one gateway */
  kind: string;
  step?: string | null;
  stage?: string | null;
  gateway_id?: number;
  gateway_name?: string;
  /** what took the bus: 'bus scan', 'teach in', ... */
  reason?: string | null;
  progress?: any;
  started_at?: string | null;
  /** tokens of what cannot be started meanwhile: 'bus', 'detection', 'gateway:<id>' */
  blocks: string[];
}

export interface Activity {
  busy: boolean;
  jobs: ActivityJob[];
}

/** observation/reception.py - the site survey of the radio gateways */
export interface ReceptionSurvey {
  recording?: boolean;
  window_seconds: number;
  from?: string;
  to?: string;
  telegrams: number;
  has_rssi: boolean;
  buffer_limited: boolean;
  covers_from?: string | null;
  last_telegram?: string | null;
  buffer_size?: number | null;
  /** one sender heard by one gateway */
  links: Array<{
    address: string;
    name?: string | null;
    known?: boolean;
    gateway_id: any;
    gateway_name?: string | null;
    count: number;
    repeated: number;
    repeated_share: number;
    per_minute: number;
    last_seen: string | null;
    rssi: { last: number | null; avg: number | null; min: number | null; max: number | null; count: number };
    quality: string | null;
    msg_types?: Record<string, number>;
  }>;
  gateways: Array<{
    gateway_id: any;
    gateway_name?: string | null;
    telegrams: number;
    senders: number;
    repeated: number;
    repeated_share: number;
    per_minute: number;
    rssi_avg: number | null;
    quality: string | null;
    best: number | null;
    worst: number | null;
  }>;
}

/* ------------------------- observation/radio_comparison.py: one telegram, many gateways */

/** One reception of a transmission - `RadioBurst.members` (radio_comparison._Member) */
export interface RadioReception {
  gateway_id: number;
  gateway_name: string | null;
  direction: string;
  simulated: boolean;
  seq: number | null;
  address: string;
  /** set when this gateway saw the device with an address relative to its own base id */
  local_address: string | null;
  /** the profile this gateway read the telegram with */
  eep: string | null;
  /** what came out of it, as one line ('temperature=22.4, humidity=41') */
  decoded: string | null;
  timestamp_ms: number;
  /** how much later than the first gateway this one reported the telegram */
  offset_ms: number;
  msg_type: string | null;
  org: string | null;
  data: string | null;
  status: string | null;
  /** status byte without the repeater counter - that is what is compared */
  status_base: string | null;
  rp_count: number | null;
  rp_count_max: number | null;
  raw: string | null;
  rssi_dbm: number | null;
  rssi_min: number | null;
  rssi_max: number | null;
  /** how often a repeater delivered the same telegram to this gateway again */
  repeats: number;
}

/** One transmission with all its receptions - RadioComparison._finalize() */
export interface RadioBurst {
  address: string;
  device_name: string | null;
  known: boolean;
  eep: string | null;
  timestamp: string;
  timestamp_ms: number;
  /** number of gateways which received it */
  gateway_count: number;
  /** every gateway which has taken part in any comparison so far */
  known_gateway_ids: number[];
  sender_gateway_ids: number[];
  missing_gateway_ids: number[];
  /** between the first and the last reception */
  span_ms: number;
  members: RadioReception[];
  rssi_min: number | null;
  rssi_max: number | null;
  rssi_spread: number | null;
  /** the compared fields which are not identical ('data', 'status', 'rp_count', ...) */
  differences: string[];
  /** received differently: a raw field other than the repeater hop count */
  disagreement: string[];
  /** read differently: the profile or the decoded values are not the same */
  interpretation: string[];
  /** fields whose values are evenly split, so no gateway can be called the wrong one */
  tied: string[];
  /** the first reception - what the differing bytes are marked against */
  reference: {
    msg_type: string | null;
    org: string | null;
    data: string | null;
    status: string | null;
    gateway_id: number | null;
  };
  /** field -> value -> the gateways which reported it */
  values: Record<string, Record<string, number[]>>;
  /** field -> the value most gateways agree on (only for differing fields) */
  majority: Record<string, string>;
  outlier_gateway_ids: number[];
}

/** _GatewayStatistics.to_dict() */
export interface RadioGatewayStatistics {
  gateway_id: number;
  gateway_name: string | null;
  received: number;
  sent: number;
  missed: number;
  /** transmissions it could have received: everything since it showed up */
  offered: number;
  share: number | null;
  /** it was the first of several gateways to report the telegram */
  first: number;
  alone: number;
  outlier: number;
  /** telegrams it took part in which the gateways did not agree about */
  differing: number;
  repeats: number;
  hops: number;
  /** how the telegrams arrived: hop count ('0' = direct) -> receptions */
  by_level: Record<string, number>;
  rssi_min: number | null;
  rssi_max: number | null;
  rssi_avg: number | null;
  rssi_count: number;
}

/** One pair of gateways head to head - radio_comparison._describe_pairs() */
export interface RadioGatewayPair {
  gateway_a: number;
  gateway_b: number;
  /** transmissions both of them received */
  together: number;
  only_a: number;
  only_b: number;
  /** a third gateway received it, neither of these two did */
  neither: number;
  /** of the ones both received: identical / not identical */
  agreed: number;
  disagreed: number;
  /** same telegram, different profile or values */
  interpreted: number;
  /** one heard the device directly, the other one through a repeater */
  hops: number;
  offered: number;
  share_a: number | null;
  share_b: number | null;
  /** how much stronger a hears the same telegram than b, on average */
  rssi_delta_avg: number | null;
  rssi_delta_count: number;
  a_stronger: number;
  b_stronger: number;
}

/** _AddressStatistics.to_dict() - one row of the "who receives what" table */
export interface RadioAddressStatistics {
  address: string;
  name: string | null;
  known: boolean;
  eep: string | null;
  bursts: number;
  differing: number;
  /** differences other than the repeater hop count */
  disagreeing: number;
  max_gateway_count: number;
  last_seen: string | null;
  /** keyed by gateway id as a string */
  gateways: Record<string, {
    count: number;
    offered: number;
    missed: number;
    share: number | null;
    hops: number;
    /** which path the telegrams took: hop count ('0' = direct) -> telegrams */
    by_level: Record<string, number>;
    direct: number;
    best_level: number | null;
    worst_level: number | null;
    rssi_min: number | null;
    rssi_max: number | null;
    rssi_avg: number | null;
  }>;
}

/** RadioComparison.get_report(), or `{enabled: false}` when recording is off */
export interface RadioComparisonReport {
  summary: {
    enabled: boolean;
    /** how to switch recording on - only present while it is off */
    hint?: string;
    /** the window the analysis was computed for, and what the ui may offer */
    window_ms?: number;
    window_choices?: number[];
    /** the view the burst list was filtered by, and every view with its label */
    filter?: string;
    filters?: Record<string, string>;
    /** how many telegrams each view holds */
    filter_counts?: Record<string, number>;
    /** what can be restricted to - independent of the current restriction */
    available?: {
      gateways: Array<{ gateway_id: number; gateway_name: string | null; count: number }>;
      addresses: Array<{ address: string; name: string | null; known: boolean; count: number }>;
    };
    selected_gateway_ids?: string[];
    selected_address?: string | null;
    hop_level_labels?: Record<string, string>;
    started_at?: string;
    /** receptions in the buffer (not transmissions) */
    telegram_count?: number;
    buffer_size?: number;
    dropped_count?: number;
    covers_from?: string | null;
    last_telegram?: string | null;
    burst_count?: number;
    differing_bursts?: number;
    disagreeing_bursts?: number;
    interpreted_bursts?: number;
    multi_gateway_bursts?: number;
    single_gateway_bursts?: number;
    by_field?: Record<string, number>;
    by_gateway_count?: Record<string, number>;
    gateway_count?: number;
    address_count?: number;
    compared_fields?: string[];
    interpretation_fields?: string[];
    hop_field?: string;
  };
  gateways: RadioGatewayStatistics[];
  addresses: RadioAddressStatistics[];
  /** every pair of gateways against each other */
  pairs: RadioGatewayPair[];
  /** the telegrams of the selected view, newest first */
  bursts: RadioBurst[];
  /** how many telegrams the selected view holds in total (bursts is limited) */
  selected_count?: number;
}

/* ------------------------------------------------------------------ command map */

/**
 * Result type per websocket command - the values of `WS` in lib/api.js. `api.call()` picks
 * the result type from this map, so a typo in a field name of the response is an error.
 *
 * Commands typed as `any` are not described yet; fill them in when you touch the page
 * which uses them.
 */
export interface WsResults {
  "eltako/integration_info": IntegrationInfo;
  "eltako/activity": Activity;
  "eltako/configured_gateways": Gateway[];
  /** core/gateway.detect(): candidate serial paths */
  "eltako/potential_usb_ports": string[];
  "eltako/info": Record<string, any>;

  "eltako/devices/form": DeviceFormDescriptor;
  "eltako/devices/list": { devices: ConfiguredDevice[] };
  "eltako/devices/add": { device: Record<string, any> };
  "eltako/devices/update": { device: Record<string, any> };
  "eltako/devices/remove": { removed: true };
  "eltako/devices/remove_all": Record<string, any>;
  "eltako/devices/teach_in":
    | { kind: "bus_memory"; sender_id: string; results: any[] }
    | { kind: "telegram"; sender_id: string; eep: string; telegram: string };

  "eltako/send_telegram": { sent: true; telegram: string; hex: string };
  "eltako/send_telegram_form": { gateways: Gateway[]; eeps: EepDescriptor[] };

  "eltako/bus/members": BusMembersResult;
  "eltako/bus/read_memory": any;
  "eltako/bus/teach_in_senders": { results: any[] };

  "eltako/gateways/form": GatewayFormDescriptor;
  "eltako/gateways/add": {
    gateway: Record<string, string>;
    config_entry_created: boolean;
    flow_result: string | null;
    reason: string | null;
  };
  "eltako/gateways/update": { gateway: Record<string, string>; [key: string]: any };
  "eltako/gateways/remove": { removed: boolean; removed_config_entries: number };
  "eltako/gateways/repair": any;
  "eltako/gateways/scan": any;

  "eltako/grafana/sync": any;

  "eltako/plug_and_play/status": PlugAndPlayStatus;
  "eltako/plug_and_play/run":
    | { started: true; status: PlugAndPlayStatus }
    | { started: false; reason: string; status: PlugAndPlayStatus };

  "eltako/simulator/form": any;
  "eltako/simulator/preset": any;
  "eltako/simulator/gateway_add": any;
  "eltako/simulator/gateway_remove": any;
  "eltako/simulator/base_id": any;
  "eltako/simulator/device_add": any;
  "eltako/simulator/device_update": any;
  "eltako/simulator/device_remove": any;
  "eltako/simulator/trigger": any;
  "eltako/simulator/teach_in": any;
  "eltako/simulator/activate": any;

  "eltako/help/catalog": any;

  // called with a literal string instead of a WS constant - see pages/control.js,
  // pages/home.js, pages/tests.js and pages/devices_config.js
  "eltako/entities/list": any;
  "eltako/entities/call": any;
  "eltako/device_tests/info": any;
  "eltako/device_tests/start": any;
  "eltako/device_tests/stop": any;
  "eltako/config/import": any;

  "eltako/settings/get": SettingsFormDescriptor;
  "eltako/settings/set": {
    settings: Record<string, any>;
    applied: any;
    form: SettingsFormDescriptor;
  };
  "eltako/settings/reset": {
    reset: string[];
    applied: any;
    form: SettingsFormDescriptor;
  };

  "eltako/telegram_log/info": LogInfo;
  "eltako/telegram_log/statistics": StatisticsResult;
  "eltako/telegram_log/recent": { telegrams: TelegramRecord[] };
  "eltako/telegram_log/suggestions": { suggestions: any[]; best: Record<string, any> };
  "eltako/reception/survey": ReceptionSurvey;
  "eltako/telegram_log/subscribe": undefined;
  "eltako/telegram_log/clear": { cleared: boolean };
  "eltako/telegram_log/refresh_devices": { known_address_count: number };

  "eltako/radio_comparison/report": RadioComparisonReport;
  "eltako/radio_comparison/clear": { cleared: boolean };
}

export type WsCommand = keyof WsResults;
