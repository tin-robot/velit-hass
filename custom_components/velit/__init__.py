"""Velit heater and air conditioner integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Populated in later phases as platforms are implemented.
PLATFORMS: list[str] = []


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a Velit device from a config entry."""
    # Full implementation added in coordinator and entity phases.
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Velit config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
