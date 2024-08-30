"""Number platform for ocpp."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from homeassistant.components.number import (
    DOMAIN as NUMBER_DOMAIN,
    NumberEntity,
    NumberEntityDescription,
    RestoreNumber,
)
from homeassistant.const import UnitOfElectricCurrent, UnitOfPower
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.event import async_track_state_change_event

from .api import CentralSystem
from .const import (
    CONF_CPID,
    CONF_MAX_CURRENT,
    CONF_CONN_NAME,
    CONF_NO_OF_CONNECTORS,
    DATA_UPDATED,
    DEFAULT_CPID,
    DEFAULT_MAX_CURRENT,
    DEFAULT_MAX_POWER,
    DEFAULT_CONN_NAME,
    DEFAULT_NO_OF_CONNECTORS,
    DOMAIN,
    ICON,
)
from .enums import Profiles


@dataclass
class OcppNumberDescription(NumberEntityDescription):
    """Class to describe a Number entity."""

    initial_value: float | None = None


ELECTRIC_CURRENT_AMPERE = UnitOfElectricCurrent.AMPERE
POWER_WATT = UnitOfPower.WATT

NUMBERS: Final = [
    OcppNumberDescription(
        key="maximum_current",
        name="Maximum Current",
        icon=ICON,
        initial_value=DEFAULT_MAX_CURRENT,
        native_min_value=0,
        native_max_value=DEFAULT_MAX_CURRENT,
        native_step=1,
        native_unit_of_measurement=ELECTRIC_CURRENT_AMPERE,
    ),
    OcppNumberDescription(
        key="maximum_power",
        name="Maximum Power",
        icon=ICON,
        initial_value=DEFAULT_MAX_POWER,
        native_min_value=0,
        native_max_value=DEFAULT_MAX_POWER,
        native_step=1,
        native_unit_of_measurement=POWER_WATT,
    ),
]


async def async_setup_entry(hass, entry, async_add_devices):
    """Configure the sensor platform."""
    central_system = hass.data[DOMAIN][entry.entry_id]
    no_of_connectors = entry.data.get(CONF_NO_OF_CONNECTORS, DEFAULT_NO_OF_CONNECTORS)
    cp_name = entry.data.get(CONF_CONN_NAME, DEFAULT_CONN_NAME)

    entities = []

    # Iterate over each connector ID (0, 1, 2, ..., connectors)
    for conn_id in range(1, no_of_connectors + 1):
        for ent in NUMBERS:
            entities.append(
                OcppNumber(hass, central_system, f"{cp_name}", ent, conn_id=conn_id)
            )

    async_add_devices(entities, False)


class OcppNumber(RestoreNumber, NumberEntity):
    """Individual slider for setting charge rate."""

    _attr_has_entity_name = True
    entity_description: OcppNumberDescription

    def __init__(
        self,
        hass: HomeAssistant,
        central_system: CentralSystem,
        cp_id: str,
        description: OcppNumberDescription,
        conn_id: int = 0,
    ):
        """Initialize a Number instance."""
        self.cp_id = cp_id
        self._hass = hass
        self.central_system = central_system
        self.entity_description = description
        self.conn_id = conn_id
        self._attr_unique_id = ".".join(
            [NUMBER_DOMAIN, self.cp_id, self.entity_description.key, str(conn_id)]
        )
        self._attr_name = f"{self.entity_description.name} (Connector {conn_id})"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.cp_id)},
            via_device=(DOMAIN, self.central_system.id),
        )
        self._attr_native_value = self.entity_description.initial_value
        self._attr_should_poll = False
        self._attr_available = True

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        if restored := await self.async_get_last_number_data():
            self._attr_native_value = restored.native_value
        async_dispatcher_connect(
            self._hass, DATA_UPDATED, self._schedule_immediate_update
        )

    @callback
    def _schedule_immediate_update(self):
        self.async_schedule_update_ha_state(True)

    async def async_set_native_value(self, value):
        """Set new value."""
        num_value = float(value)
        if self.central_system.get_available(
            self.cp_id
        ) and Profiles.SMART & self.central_system.get_supported_features(self.cp_id):
            if self.entity_description.key == "maximum_current":
                resp = await self.central_system.set_max_charge_rate_amps(
                    self.cp_id, num_value, conn_id=self.conn_id
                )
            elif self.entity_description.key == "maximum_power":
                resp = await self.central_system.set_max_charge_rate_watts(
                    self.cp_id, num_value, conn_id=self.conn_id
                )
            if resp is True:
                self._attr_native_value = num_value
                self.async_write_ha_state()
