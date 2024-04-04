# Home Assistant Eltako Integration Documentation

## Content

* [Landing Page](../README.md)

* **Suppoted Devices**
  * [Supported Messages Types (EEP) and Devices (on Landing Page)](../README.md)
  * [Supported Gateways](./gateways/readme.md)

* **Installation**
  * [Basic Installation Instruction (on main page)](../README.md)
  * [Manual Installation or Installation of a Specific Version/Git-Branch](./install-specific-version-or-branch.md)
  * [Manual Installation Script `install_custom_component_eltako.sh`](../install_custom_component_eltako.sh)

* **Home Assistant Eltako Integration Configuration**
  * [Basic Configuration Explanation](./update_home_assistant_configuration.md)
  * [Gateway Configuration](./gateway_usage/readme.md) (See how to use many gateways in parallel under features.)
  * To auto-generate the configuration [EnOcean Device Manager (eo_man)](https://github.com/grimmpp/enocean-device-manager) can be used.
  * [Example Configuration `ha.yaml`](../ha.yaml)

* **Meta Information**
  * [Metadata file/Manifest of Eltako Integration](../custom_components/eltako/manifest.json)

* **Features and Use Cases**
  * [Logging](./logging/readme.md)
  * [Light Tutorial](./lights-tutorial/readme.md)
  * [Window/Door Contacts or Classic Switches](./window_sensor_setup_FTS14EM.md)
  * [Temperature and Humidity Sensors (FLGTF)](./flgtf_temp_humidity_air_quality/readme.md)
  * [Heating and Cooling (Climate Devices)](./heating-and-cooling/readme.md)
  * [Multi-Gateway Support](./gateway_usage/readme.md)
  * [Automations triggered by Wall-Mounted EnOcean Switches](./rocker_switch/readme.md)
  * [Teach-In Buttons](./teach_in_buttons/readme.md)
  * [Sending Arbitrary EnOcean Messages](./service-send-message/readme.md)
    * [Auto-generated List of EEP Parameters](./service-send-message/eep-params.md)

* **Management of EnOcean Devices** 
  * To manage, inventory, and auto-generate the configuration you can use [EnOcean Device Manager (eo_man)](https://github.com/grimmpp/enocean-device-manager).

* **Testing**
  * [Testing (on Landing Page)](../README.md)

* [**Change Log**](../changes.md)