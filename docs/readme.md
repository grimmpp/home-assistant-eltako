# Home Assistant ELTAKO Integration Documentation

## Content

* [Landing Page](../README.md)

* **Start here** &ndash; install, add the integration, configure everything in the panel
  * [Web UI of the Integration](./web-ui/readme.md) &ndash; in the sidebar by default, no configuration file needed
  * [Plug & Play: Detecting Gateways and Devices Automatically](./plug-and-play/readme.md)
  * [Example Setup: Wiring and Teach-In of Series 14 Devices](./01_getting_started/readme.md)

* **Supported Devices**
  * [Supported Devices and EEPs](./supported-devices.md) (generated from the code &ndash; also summarized on the [landing page](../README.md))
  * [Supported Gateways](./gateways/readme.md)

* **Installation**
  * [Basic Installation Instruction (on main page)](../README.md)
  * [Manual Installation or Installation of a Specific Version/Git-Branch](./install-specific-version-or-branch.md)
  * [Manual Installation Script `install_custom_component_eltako.sh`](../install_custom_component_eltako.sh)

* **Configuration in Files** (optional &ndash; everything below can be done in the web ui instead)
  * [Basic Configuration Explanation](./update_home_assistant_configuration.md)
  * [Gateway Configuration](./gateway_usage/readme.md) (See how to use many gateways in parallel under features.)
  * To auto-generate the configuration [EnOcean Device Manager (eo_man)](https://github.com/grimmpp/enocean-device-manager) can be used. Its projects and PCT14 exports can be imported in the web ui.
  * [Example Configuration `ha.yaml`](../ha.yaml)

* **Meta Information**
  * [Metadata file/Manifest of ELTAKO Integration](../custom_components/eltako/manifest.json)

* **Features and Use Cases**
  * [Logging](./logging/readme.md)
  * [Light Tutorial](./lights-tutorial/readme.md)
  * [Window/Door Contacts or Classic Switches](./window_sensor_setup_FTS14EM.md)
  * [Temperature and Humidity Sensors (FLGTF)](./flgtf_temp_humidity_air_quality/readme.md)
  * [Heating and Cooling (Climate Devices)](./heating-and-cooling/readme.md)
  * [Multi-Gateway Support](./gateway_usage/readme.md)
  * [Automations triggered by Wall-Mounted EnOcean Switches](./rocker_switch/readme.md)
  * [Reacting on Incoming Telegrams in Automations (Event `eltako_global_event_bus`)](./telegram-events/readme.md)
  * [Device Tests: Configuration Check, Teach-In Test, Burst Test, Cover Travel Times](./device-tests/readme.md)
  * [Simulation: Gateways and Devices without Hardware](./simulation/readme.md)
  * [Teach-In Buttons](./teach_in_buttons/readme.md)
  * [Sending Arbitrary EnOcean Messages](./service-send-message/readme.md)
    * [Auto-generated List of EEP Parameters](./service-send-message/eep-params.md)

* **Management of EnOcean Devices** 
  * To manage, inventory, and auto-generate the configuration you can use [EnOcean Device Manager (eo_man)](https://github.com/grimmpp/enocean-device-manager).

* **Development**
  * [Architecture - how this integration is built](architecture/readme.md)
  * [Websocket api - every command of the web ui, with its parameters](architecture/websocket-api.md)
  * [Generating the documentation](../generate_docs.py) - the supported devices and EEPs are rendered from the code (`python generate_docs.py`)
  * [Development container (Home Assistant + example data + Grafana)](dev-container/readme.md)
  * [Standalone runtime (without Home Assistant)](standalone/readme.md)
  * [Testing with real hardware](hardware-testing/readme.md) &ndash; both ways to put a real gateway in front of the automatic detection, and the one rule that breaks everything else
  * [Analysing telegrams with Grafana](grafana/readme.md)
* **Testing**
  * [Testing (on Landing Page)](../README.md)

* [**Change Log**](../changes.md)