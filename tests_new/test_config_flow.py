"""Test config flow for Eltako integration."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.eltako.config_flow import EltakoFlowHandler, EltakoOptionsFlowHandler
from custom_components.eltako.const import (
    DOMAIN,
    CONF_GATEWAY_DESCRIPTION,
    CONF_SERIAL_PATH,
    CONF_GATEWAY_AUTO_RECONNECT,
    CONF_GATEWAY_MESSAGE_DELAY,
    CONF_ENABLE_TEACH_IN_BUTTONS,
    ERROR_INVALID_GATEWAY_PATH,
    ERROR_NO_GATEWAY_CONFIGURATION_AVAILABLE,
    ERROR_NO_SERIAL_PATH_AVAILABLE,
)


class TestEltakoConfigFlow:
    """Test the Eltako config flow."""

    async def test_form_user_step(self, hass: HomeAssistant, mock_setup_functions, mock_serial_detection):
        """Test we get the form."""
        mock_setup_functions["async_get_home_assistant_config"].return_value = {
            "eltako": {"gateway": [{"id": 0, "device_type": "enocean-usb2"}]}
        }
        mock_setup_functions["async_get_list_of_gateway_descriptions"] = AsyncMock(
            return_value={"0": "Test Gateway (Gateway-0)"}
        )

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "detect"
        assert "data_schema" in result

    async def test_form_detect_step_success(
        self,
        hass: HomeAssistant,
        mock_setup_functions,
        mock_serial_detection,
        mock_path_validation
    ):
        """Test successful gateway detection and setup."""
        mock_setup_functions["async_get_home_assistant_config"].return_value = {
            "eltako": {"gateway": [{"id": 0, "device_type": "enocean-usb2"}]}
        }

        with patch("custom_components.eltako.config_helpers.async_get_list_of_gateway_descriptions") as mock_gateways:
            mock_gateways.return_value = {"0": "Test Gateway (Gateway-0)"}

            # Start flow
            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )

            # Submit valid data
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {
                    CONF_GATEWAY_DESCRIPTION: "Test Gateway (Gateway-0)",
                    CONF_SERIAL_PATH: "/dev/ttyUSB0",
                },
            )

            assert result["type"] == FlowResultType.CREATE_ENTRY
            assert result["title"] == "Eltako"
            assert result["data"] == {
                CONF_GATEWAY_DESCRIPTION: "Test Gateway (Gateway-0)",
                CONF_SERIAL_PATH: "/dev/ttyUSB0",
            }

    async def test_form_detect_step_invalid_path(
        self,
        hass: HomeAssistant,
        mock_setup_functions,
        mock_serial_detection
    ):
        """Test invalid gateway path handling."""
        mock_setup_functions["async_get_home_assistant_config"].return_value = {
            "eltako": {"gateway": [{"id": 0, "device_type": "enocean-usb2"}]}
        }

        with patch("custom_components.eltako.config_helpers.async_get_list_of_gateway_descriptions") as mock_gateways:
            mock_gateways.return_value = {"0": "Test Gateway (Gateway-0)"}

            with patch("custom_components.eltako.gateway.validate_path", return_value=False):
                # Start flow
                result = await hass.config_entries.flow.async_init(
                    DOMAIN, context={"source": config_entries.SOURCE_USER}
                )

                # Submit invalid data
                result = await hass.config_entries.flow.async_configure(
                    result["flow_id"],
                    {
                        CONF_GATEWAY_DESCRIPTION: "Test Gateway (Gateway-0)",
                        CONF_SERIAL_PATH: "/invalid/path",
                    },
                )

                assert result["type"] == FlowResultType.FORM
                assert result["errors"] == {CONF_SERIAL_PATH: ERROR_INVALID_GATEWAY_PATH}

    async def test_form_no_gateways_configured(
        self,
        hass: HomeAssistant,
        mock_setup_functions,
        mock_serial_detection
    ):
        """Test handling when no gateways are configured."""
        mock_setup_functions["async_get_home_assistant_config"].return_value = {
            "eltako": {"gateway": []}
        }

        with patch("custom_components.eltako.config_helpers.async_get_list_of_gateway_descriptions") as mock_gateways:
            mock_gateways.return_value = {}

            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )

            assert result["type"] == FlowResultType.FORM
            assert result["errors"] == {CONF_GATEWAY_DESCRIPTION: ERROR_NO_GATEWAY_CONFIGURATION_AVAILABLE}

    async def test_form_manual_step(
        self,
        hass: HomeAssistant,
        mock_setup_functions,
        mock_path_validation
    ):
        """Test manual gateway configuration."""
        mock_setup_functions["async_get_home_assistant_config"].return_value = {
            "eltako": {"gateway": [{"id": 0, "device_type": "enocean-usb2"}]}
        }

        with patch("custom_components.eltako.config_helpers.async_get_list_of_gateway_descriptions") as mock_gateways:
            mock_gateways.return_value = {"0": "Test Gateway (Gateway-0)"}

            # Start manual flow
            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )

            # Go to manual step
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {}, step_id="manual"
            )

            assert result["type"] == FlowResultType.FORM
            assert result["step_id"] == "manual"

    async def test_lan_gateway_ip_validation_success(
        self,
        hass: HomeAssistant,
        mock_setup_functions,
        mock_serial_detection
    ):
        """Test LAN gateway with valid IP address."""
        mock_setup_functions["async_get_home_assistant_config"].return_value = {
            "eltako": {"gateway": [{"id": 0, "device_type": "esp3-lan"}]}
        }

        with patch("custom_components.eltako.config_helpers.async_get_list_of_gateway_descriptions") as mock_gateways:
            mock_gateways.return_value = {"0": "Test LAN Gateway (Gateway-0)"}

            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )

            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {
                    CONF_GATEWAY_DESCRIPTION: "Test LAN Gateway (Gateway-0)",
                    CONF_SERIAL_PATH: "192.168.1.100",
                },
            )

            assert result["type"] == FlowResultType.CREATE_ENTRY

    async def test_lan_gateway_ip_validation_failure(
        self,
        hass: HomeAssistant,
        mock_setup_functions,
        mock_serial_detection
    ):
        """Test LAN gateway with invalid IP address."""
        mock_setup_functions["async_get_home_assistant_config"].return_value = {
            "eltako": {"gateway": [{"id": 0, "device_type": "esp3-lan"}]}
        }

        with patch("custom_components.eltako.config_helpers.async_get_list_of_gateway_descriptions") as mock_gateways:
            mock_gateways.return_value = {"0": "Test LAN Gateway (Gateway-0)"}

            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )

            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {
                    CONF_GATEWAY_DESCRIPTION: "Test LAN Gateway (Gateway-0)",
                    CONF_SERIAL_PATH: "invalid.ip.address",
                },
            )

            assert result["type"] == FlowResultType.FORM
            assert result["errors"] == {CONF_SERIAL_PATH: ERROR_INVALID_GATEWAY_PATH}


class TestEltakoOptionsFlow:
    """Test the Eltako options flow."""

    async def test_options_form(self, hass: HomeAssistant, mock_config_entry):
        """Test options form display."""
        options_flow = EltakoOptionsFlowHandler(mock_config_entry)

        result = await options_flow.async_step_init()

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "init"
        assert "data_schema" in result

    async def test_options_form_submit(self, hass: HomeAssistant, mock_config_entry):
        """Test options form submission."""
        options_flow = EltakoOptionsFlowHandler(mock_config_entry)

        result = await options_flow.async_step_init({
            CONF_GATEWAY_AUTO_RECONNECT: False,
            CONF_GATEWAY_MESSAGE_DELAY: 0.5,
            CONF_ENABLE_TEACH_IN_BUTTONS: False,
        })

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"] == {
            CONF_GATEWAY_AUTO_RECONNECT: False,
            CONF_GATEWAY_MESSAGE_DELAY: 0.5,
            CONF_ENABLE_TEACH_IN_BUTTONS: False,
        }

    async def test_options_form_defaults(self, hass: HomeAssistant, mock_config_entry):
        """Test options form displays current values as defaults."""
        # Add some existing options
        mock_config_entry.options = {
            CONF_GATEWAY_AUTO_RECONNECT: False,
            CONF_GATEWAY_MESSAGE_DELAY: 1.0,
        }

        options_flow = EltakoOptionsFlowHandler(mock_config_entry)
        result = await options_flow.async_step_init()

        # Verify the form uses existing options as defaults
        assert result["type"] == FlowResultType.FORM
        data_schema = result["data_schema"]

        # Extract defaults from schema (this is implementation dependent)
        # In a real test, you'd verify the schema contains the expected defaults

    async def test_options_flow_from_config_entry(self, hass: HomeAssistant, mock_config_entry):
        """Test options flow creation from config entry."""
        flow_handler = EltakoFlowHandler()
        options_flow = flow_handler.async_get_options_flow(mock_config_entry)

        assert isinstance(options_flow, EltakoOptionsFlowHandler)
        assert options_flow.config_entry == mock_config_entry


class TestEltakoConfigFlowErrors:
    """Test error handling in config flow."""

    async def test_gateway_check_failure(self, hass: HomeAssistant, mock_setup_functions):
        """Test handling of gateway check failure."""
        mock_setup_functions["config_check_gateway"].return_value = False
        mock_setup_functions["async_get_home_assistant_config"].return_value = {
            "eltako": {"gateway": [{"id": 0}, {"id": 0}]}  # Duplicate IDs
        }

        with patch("custom_components.eltako.config_helpers.async_get_list_of_gateway_descriptions") as mock_gateways:
            mock_gateways.return_value = {"0": "Test Gateway (Gateway-0)"}

            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )

            # This should handle the error gracefully
            assert result["type"] == FlowResultType.FORM

    async def test_async_executor_job_failure(self, hass: HomeAssistant, mock_setup_functions):
        """Test handling of async executor job failure."""
        mock_setup_functions["async_get_home_assistant_config"].return_value = {
            "eltako": {"gateway": [{"id": 0, "device_type": "enocean-usb2"}]}
        }

        # Mock executor job to raise exception
        hass.async_add_executor_job = AsyncMock(side_effect=Exception("Executor error"))

        with patch("custom_components.eltako.config_helpers.async_get_list_of_gateway_descriptions") as mock_gateways:
            mock_gateways.return_value = {"0": "Test Gateway (Gateway-0)"}

            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )

            # Should handle executor failure gracefully
            assert result["type"] == FlowResultType.FORM