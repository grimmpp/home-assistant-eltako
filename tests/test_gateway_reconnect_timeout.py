from unittest import TestCase, mock

from eltakobus.message import Regular4BSMessage
from eltakobus.util import AddressExpression

from custom_components.eltako.core import gateway as gateway_module
from custom_components.eltako.core.gateway import EnOceanGateway, GatewayDeviceType
from tests.mocks import HassMock


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

    def test_bus_gateway_mapping_resolves_the_canonical_gateway(self):
        source = object.__new__(EnOceanGateway)
        source._bus_gateway_id = 1
        source.hass = HassMock()

        canonical = object.__new__(EnOceanGateway)
        canonical._attr_dev_id = 1
        source.hass.data['eltako'] = {'gateway_1': canonical}

        self.assertIs(source._bus_gateway_for_global_events(), canonical)

    def test_bus_gateway_mapping_does_not_resolve_to_itself(self):
        gateway = object.__new__(EnOceanGateway)
        gateway._bus_gateway_id = 1
        gateway._attr_dev_id = 1
        gateway.hass = HassMock()
        gateway.hass.data['eltako'] = {'gateway_1': gateway}

        self.assertIsNone(gateway._bus_gateway_for_global_events())

    def test_received_local_telegram_is_rewritten_with_canonical_bus_base_id(self):
        source = object.__new__(EnOceanGateway)
        source._attr_dev_id = 2
        source._attr_dev_name = "FGW14"
        source._attr_base_id = AddressExpression.parse("00-00-00-00")
        source._bus_gateway_id = 1
        source.hass = HassMock()

        canonical = object.__new__(EnOceanGateway)
        canonical._attr_dev_id = 1
        canonical._attr_base_id = AddressExpression.parse("FF-AA-80-00")
        source.hass.data["eltako"] = {"gateway_1": canonical}

        source._record_telegram = mock.Mock()
        source.report_message_stats = mock.Mock()
        message = Regular4BSMessage(
            address=b"\x00\x00\x00\x04", status=0x00, data=b"\x02\x64\x00\x09"
        )

        with mock.patch.object(gateway_module, "dispatcher_send") as dispatch:
            source._handle_received_message(message)

        global_event = next(
            call.args[2]
            for call in dispatch.call_args_list
            if call.args[1] == gateway_module.ELTAKO_GLOBAL_EVENT_BUS_ID
        )
        self.assertEqual(global_event["gateway"], canonical)
        self.assertEqual(global_event["esp2_msg"].address, b"\xFF\xAA\x80\x04")
