from unittest import TestCase, mock

from custom_components.eltako.core import gateway as gateway_module
from custom_components.eltako.core.gateway import EnOceanGateway, GatewayDeviceType


class TestGatewayReconnectTimeout(TestCase):
    """The configured reconnect timeout reaches every gateway communicator."""

    def test_reconnect_timeout_is_forwarded_for_all_gateway_protocols(self):
        cases = (
            (GatewayDeviceType.GatewayEltakoFAM14, "RS485SerialInterfaceV2"),
            (GatewayDeviceType.MGW_LAN, "TCP2SerialCommunicator"),
            (GatewayDeviceType.USB300, "ESP3SerialCommunicator"),
        )

        for device_type, communicator_name in cases:
            with self.subTest(device_type=device_type):
                communicator = mock.MagicMock()
                communicator_class = mock.patch.object(
                    gateway_module, communicator_name, return_value=communicator
                )

                gateway = object.__new__(EnOceanGateway)
                gateway._attr_dev_type = device_type
                gateway._attr_serial_path = "gateway-path"
                gateway.port = 5100
                gateway.baud_rate = 57600
                gateway._attr_dev_id = 1
                gateway._message_delay = 0.01
                gateway._auto_reconnect = True
                gateway._reconnect_timeout = 2.5

                with mock.patch.object(
                    gateway, "_fire_received_message_count_event"
                ), communicator_class as communicator_constructor:
                    gateway._init_bus()

                communicator_constructor.assert_called_once()
                self.assertEqual(
                    communicator_constructor.call_args.kwargs["reconnection_timeout"],
                    2.5,
                )
                communicator.set_status_changed_handler.assert_called_once_with(
                    gateway._fire_connection_state_changed_event
                )
