import pytest
import voluptuous as vol


def test_entity_id_validator_accepts_valid_entity_id():
    from homeassistant.helpers import config_validation as cv

    assert cv.entity_id("sensor.room_temperature") == "sensor.room_temperature"


@pytest.mark.parametrize(
    "value",
    ["sensor", ".temperature", "sensor.", "Sensor.temperature", "sensor.room.temp"],
)
def test_entity_id_validator_rejects_invalid_entity_id(value):
    from homeassistant.helpers import config_validation as cv

    with pytest.raises(vol.Invalid):
        cv.entity_id(value)
