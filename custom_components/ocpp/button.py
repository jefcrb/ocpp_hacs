"""Button platform for ocpp."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from homeassistant.components.button import (
    DOMAIN as BUTTON_DOMAIN,
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.helpers.entity import DeviceInfo, EntityCategory

from .api import CentralSystem
from .const import (
    CONF_CPID,
    DEFAULT_CPID,
    DOMAIN,
    CONF_CONN_NAME,
    CONF_NO_OF_CONNECTORS,
    DEFAULT_CONN_NAME,
    DEFAULT_NO_OF_CONNECTORS,
)
from .enums import HAChargerServices


@dataclass
class OcppButtonDescription(ButtonEntityDescription):
    """Class to describe a Button entity."""

    press_action: str | None = None


BUTTONS: Final = [
    OcppButtonDescription(
        key="reset",
        name="Reset",
        device_class=ButtonDeviceClass.RESTART,
        entity_category=EntityCategory.CONFIG,
        press_action=HAChargerServices.service_reset.name,
    ),
    OcppButtonDescription(
        key="unlock",
        name="Unlock",
        device_class=ButtonDeviceClass.UPDATE,
        entity_category=EntityCategory.CONFIG,
        press_action=HAChargerServices.service_unlock.name,
    ),
]


async def async_setup_entry(hass, entry, async_add_devices):
    """Configure the Button platform."""

    central_system = hass.data[DOMAIN][entry.entry_id]["central_sys"]
    cp_name = entry.data.get(CONF_CONN_NAME, DEFAULT_CONN_NAME)
    no_of_connectors = entry.data.get(CONF_NO_OF_CONNECTORS, DEFAULT_NO_OF_CONNECTORS)

    entities = []

    for ent in BUTTONS:
        if ent.key == "unlock":
            for conn_no in range(no_of_connectors + 1):
                entities.append(
                    ChargePointButton(central_system, cp_name, ent, conn_no)
                )
        else:
            entities.append(ChargePointButton(central_system, cp_name, ent, 0))

    async_add_devices(entities, False)


class ChargePointButton(ButtonEntity):
    """Individual button for charge point."""

    _attr_has_entity_name = True
    entity_description: OcppButtonDescription

    def __init__(
        self,
        central_system: CentralSystem,
        cp_id: str,
        description: OcppButtonDescription,
        conn_id: int = 0,
    ):
        """Instantiate instance of a ChargePointButton."""
        self.cp_id = cp_id
        self.central_system = central_system
        self.entity_description = description
        self.conn_id = conn_id
        self._attr_unique_id = ".".join(
            [
                BUTTON_DOMAIN,
                DOMAIN,
                self.cp_id,
                str(conn_id),
                self.entity_description.key,
            ]
        )
        self._attr_name = f"{self.entity_description.name} {self.conn_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.cp_id)},
            via_device=(DOMAIN, self.central_system.id),
        )

    @property
    def available(self) -> bool:
        """Return charger availability."""
        return self.central_system.get_available(self.cp_id)  # type: ignore [no-any-return]

    async def async_press(self) -> None:
        """Triggers the charger press action service."""
        await self.central_system.set_charger_state(
            self.cp_id, self.entity_description.press_action, self.conn_id
        )
