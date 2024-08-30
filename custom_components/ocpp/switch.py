"""Switch platform for ocpp."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from homeassistant.components.switch import (
    DOMAIN as SWITCH_DOMAIN,
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.const import UnitOfPower
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.event import async_track_state_change_event

from ocpp.v16.enums import ChargePointStatus

from .api import CentralSystem
from .const import (
    CONF_CPID,
    DEFAULT_CPID,
    DOMAIN,
    ICON,
    CONF_CONN_NAME,
    CONF_NO_OF_CONNECTORS,
    DEFAULT_CONN_NAME,
    DEFAULT_NO_OF_CONNECTORS,
)
from .enums import HAChargerServices, HAChargerStatuses
import logging

_LOGGER: logging.Logger = logging.getLogger(__package__)


# Switch configuration definitions
# At a minimum define switch name and on service call,
# metric and condition combination can be used to drive switch state, use default to set initial state to True
@dataclass
class OcppSwitchDescription(SwitchEntityDescription):
    """Class to describe a Switch entity."""

    on_action: str | None = None
    off_action: str | None = None
    metric_state: str | None = None
    metric_condition: str | None = None
    default_state: bool = False


POWER_KILO_WATT = UnitOfPower.KILO_WATT

SWITCHES: Final = [
    OcppSwitchDescription(
        key="charge_control",
        name="Charge Control",
        icon=ICON,
        on_action=HAChargerServices.service_charge_start.name,
        off_action=HAChargerServices.service_charge_stop.name,
        metric_state=HAChargerStatuses.status_connector.value,
        metric_condition=[
            ChargePointStatus.charging.value,
            ChargePointStatus.suspended_evse.value,
            ChargePointStatus.suspended_ev.value,
        ],
    ),
    OcppSwitchDescription(
        key="availability",
        name="Availability",
        icon=ICON,
        on_action=HAChargerServices.service_availability.name,
        off_action=HAChargerServices.service_availability.name,
        metric_state=HAChargerStatuses.status_connector.value,
        metric_condition=[
            ChargePointStatus.available.value,
            ChargePointStatus.preparing.value,
        ],
        default_state=True,
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
        for ent in SWITCHES:
            entities.append(
                ChargePointSwitch(central_system, cp_name, ent, conn_id=conn_id)
            )

    async_add_devices(entities, False)


class ChargePointSwitch(SwitchEntity):
    """Individual switch for charge point."""

    _attr_has_entity_name = True
    entity_description: OcppSwitchDescription

    def __init__(
        self,
        central_system: CentralSystem,
        cp_id: str,
        description: OcppSwitchDescription,
        conn_id: int,
    ):
        """Instantiate instance of a ChargePointSwitch."""
        self.cp_id = cp_id
        self.connector = f"{cp_id}_{conn_id}"
        self.central_system = central_system
        self.entity_description = description
        self._state = self.entity_description.default_state
        self.conn_id = conn_id
        self._attr_unique_id = ".".join(
            [
                SWITCH_DOMAIN,
                DOMAIN,
                self.cp_id,
                self.entity_description.key,
                str(conn_id),
            ]
        )
        self._attr_name = f"{self.entity_description.name} (Connector {conn_id})"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.cp_id)},
            via_device=(DOMAIN, self.central_system.id),
        )

    @property
    def available(self) -> bool:
        """Return if switch is available."""
        return self.central_system.get_available(self.connector)  # type: ignore [no-any-return]

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        """Test metric state against condition if present"""
        if self.entity_description.metric_state is not None:
            resp = self.central_system.get_metric(
                self.connector,
                self.entity_description.metric_state,
            )
            # _LOGGER.info(
            #     "is on for %s states resp: %s should be in %s, is %s measurand",
            #     self.connector,
            #     resp,
            #     self.entity_description.metric_condition,
            #     self.entity_description.metric_state,
            # )
            if resp in self.entity_description.metric_condition:
                self._state = True
            else:
                self._state = False
        return self._state  # type: ignore [no-any-return]

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        self._state = await self.central_system.set_charger_state(
            self.connector, self.entity_description.on_action, conn_id=self.conn_id
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        """Response is True if successful but State is False"""
        if self.entity_description.off_action is None:
            resp = True
        elif self.entity_description.off_action == self.entity_description.on_action:
            resp = await self.central_system.set_charger_state(
                self.connector, self.entity_description.off_action, False, self.conn_id
            )
        else:
            resp = await self.central_system.set_charger_state(
                self.connector, self.entity_description.off_action, conn_id=self.conn_id
            )
        self._state = not resp
