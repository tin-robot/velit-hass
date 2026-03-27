"""Switch entities for Velit heater and AC devices.

Heater:
  VelitHeaterBLESwitch — toggles the BLE connection on/off. On = connected
    and polling; off = disconnected and not polling. Turning off suppresses
    the reconnect loop so the device stays released until the user turns it
    back on. Useful for handing the device to the Velit mobile app without
    restarting the integration.

AC:
  No switch entities at this time.
"""

from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEVICE_TYPE_HEATER, DOMAIN
from .coordinator import VelitHeaterCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Velit switch entities from a config entry."""
    if entry.data["device_type"] != DEVICE_TYPE_HEATER:
        return

    coordinator: VelitHeaterCoordinator = entry.runtime_data
    async_add_entities([VelitHeaterBLESwitch(coordinator, entry)])


class VelitHeaterBLESwitch(CoordinatorEntity[VelitHeaterCoordinator], SwitchEntity):
    """Toggle switch for the heater BLE connection.

    On  — BLE connected, coordinator polling normally.
    Off — BLE disconnected, reconnect loop suppressed. The device is free
          for other apps (e.g. the Velit mobile app) to use.

    Turning the switch back on triggers an immediate connect attempt. If it
    fails (device busy), the switch stays off and the user can retry.
    """

    _attr_name = "BLE Connection"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:bluetooth"

    def __init__(
        self,
        coordinator: VelitHeaterCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.data['address']}_ble_connection"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.data["address"])},
            name=entry.data.get(CONF_NAME, entry.data["address"]),
            manufacturer="Velit",
        )

    @property
    def is_on(self) -> bool:
        return self.coordinator._client.connected

    async def async_turn_on(self, **kwargs) -> None:
        """Connect to the device and resume polling."""
        try:
            await self.coordinator._client.connect()
            await self.coordinator.async_request_refresh()
        except Exception as exc:
            _LOGGER.warning("BLE reconnect failed: %s", exc)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Disconnect from the device and suppress automatic reconnection."""
        await self.coordinator._client.disconnect()
        self.async_write_ha_state()
