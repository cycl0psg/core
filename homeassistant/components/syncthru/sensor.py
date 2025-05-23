"""Support for Samsung Printers with SyncThru web interface."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from pysyncthru import SyncThru, SyncthruState

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SyncthruCoordinator
from .const import DOMAIN
from .entity import SyncthruEntity

SYNCTHRU_STATE_HUMAN = {
    SyncthruState.INVALID: "invalid",
    SyncthruState.OFFLINE: "unreachable",
    SyncthruState.NORMAL: "normal",
    SyncthruState.UNKNOWN: "unknown",
    SyncthruState.WARNING: "warning",
    SyncthruState.TESTING: "testing",
    SyncthruState.ERROR: "error",
}


@dataclass(frozen=True, kw_only=True)
class SyncThruSensorDescription(SensorEntityDescription):
    """Describes a SyncThru sensor entity."""

    value_fn: Callable[[SyncThru], str | None]
    extra_state_attributes_fn: Callable[[SyncThru], dict[str, str | int]] | None = None


def get_toner_entity_description(color: str) -> SyncThruSensorDescription:
    """Get toner entity description for a specific color."""
    return SyncThruSensorDescription(
        key=f"toner_{color}",
        name=f"Toner {color}",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda printer: printer.toner_status().get(color, {}).get("remaining"),
        extra_state_attributes_fn=lambda printer: printer.toner_status().get(color, {}),
    )


def get_drum_entity_description(color: str) -> SyncThruSensorDescription:
    """Get drum entity description for a specific color."""
    return SyncThruSensorDescription(
        key=f"drum_{color}",
        name=f"Drum {color}",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda printer: printer.drum_status().get(color, {}).get("remaining"),
        extra_state_attributes_fn=lambda printer: printer.drum_status().get(color, {}),
    )


def get_input_tray_entity_description(tray: str) -> SyncThruSensorDescription:
    """Get input tray entity description for a specific tray."""
    return SyncThruSensorDescription(
        key=f"tray_{tray}",
        name=f"Tray {tray}",
        value_fn=(
            lambda printer: printer.input_tray_status().get(tray, {}).get("newError")
            or "Ready"
        ),
        extra_state_attributes_fn=(
            lambda printer: printer.input_tray_status().get(tray, {})
        ),
    )


def get_output_tray_entity_description(tray: int) -> SyncThruSensorDescription:
    """Get output tray entity description for a specific tray."""
    return SyncThruSensorDescription(
        key=f"output_tray_{tray}",
        name=f"Output Tray {tray}",
        value_fn=(
            lambda printer: printer.output_tray_status().get(tray, {}).get("status")
            or "Ready"
        ),
        extra_state_attributes_fn=(
            lambda printer: cast(
                dict[str, str | int], printer.output_tray_status().get(tray, {})
            )
        ),
    )


SENSOR_TYPES: tuple[SyncThruSensorDescription, ...] = (
    SyncThruSensorDescription(
        key="active_alerts",
        name="Active Alerts",
        value_fn=lambda printer: printer.raw().get("GXI_ACTIVE_ALERT_TOTAL"),
    ),
    SyncThruSensorDescription(
        key="main",
        name="",
        value_fn=lambda printer: SYNCTHRU_STATE_HUMAN[printer.device_status()],
        extra_state_attributes_fn=lambda printer: {
            "display_text": printer.device_status_details(),
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up from config entry."""

    coordinator: SyncthruCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    printer = coordinator.data

    supp_toner = printer.toner_status(filter_supported=True)
    supp_drum = printer.drum_status(filter_supported=True)
    supp_tray = printer.input_tray_status(filter_supported=True)
    supp_output_tray = printer.output_tray_status()

    name: str = config_entry.data[CONF_NAME]
    entities: list[SyncThruSensorDescription] = [
        get_toner_entity_description(color) for color in supp_toner
    ]
    entities.extend(get_drum_entity_description(color) for color in supp_drum)
    entities.extend(get_input_tray_entity_description(key) for key in supp_tray)
    entities.extend(get_output_tray_entity_description(key) for key in supp_output_tray)

    async_add_entities(
        SyncThruSensor(coordinator, name, description)
        for description in SENSOR_TYPES + tuple(entities)
    )


class SyncThruSensor(SyncthruEntity, SensorEntity):
    """Implementation of an abstract Samsung Printer sensor platform."""

    _attr_icon = "mdi:printer"
    entity_description: SyncThruSensorDescription

    def __init__(
        self,
        coordinator: SyncthruCoordinator,
        name: str,
        entity_description: SyncThruSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = entity_description
        self.syncthru = coordinator.data
        self._attr_name = f"{name} {entity_description.name}".strip()
        serial_number = coordinator.data.serial_number()
        assert serial_number is not None
        self._attr_unique_id = f"{serial_number}_{entity_description.key}"

    @property
    def native_value(self) -> str | int | None:
        """Return the state of the sensor."""
        return self.entity_description.value_fn(self.syncthru)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the state attributes."""
        if self.entity_description.extra_state_attributes_fn:
            return self.entity_description.extra_state_attributes_fn(self.syncthru)
        return None
