"""Unit tests for VelitHeaterBLESwitch."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.velit.switch import VelitHeaterBLESwitch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(address="AA:BB:CC:DD:EE:FF"):
    entry = MagicMock()
    entry.data = {"device_type": "heater", "address": address, "name": "Test Heater"}
    return entry


def _make_entity(connected=True):
    coord = MagicMock()
    coord._client = MagicMock()
    coord._client.connected = connected
    coord._client.connect = AsyncMock()
    coord._client.disconnect = AsyncMock()
    coord.async_request_refresh = AsyncMock()
    entry = _make_entry()
    entity = VelitHeaterBLESwitch.__new__(VelitHeaterBLESwitch)
    entity.coordinator = coord
    entity._attr_unique_id = f"{entry.data['address']}_ble_connection"
    entity._attr_name = "BLE Connection"
    entity._attr_device_info = MagicMock()
    # async_write_ha_state needs to be a no-op in tests
    entity.async_write_ha_state = MagicMock()
    return entity, coord


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class TestBLESwitchState:
    def test_is_on_when_connected(self):
        entity, _ = _make_entity(connected=True)
        assert entity.is_on is True

    def test_is_off_when_disconnected(self):
        entity, _ = _make_entity(connected=False)
        assert entity.is_on is False


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


class TestBLESwitchActions:
    async def test_turn_off_calls_disconnect(self):
        entity, coord = _make_entity(connected=True)
        await entity.async_turn_off()
        coord._client.disconnect.assert_awaited_once()

    async def test_turn_off_writes_state(self):
        entity, _ = _make_entity(connected=True)
        await entity.async_turn_off()
        entity.async_write_ha_state.assert_called_once()

    async def test_turn_on_calls_connect(self):
        entity, coord = _make_entity(connected=False)
        await entity.async_turn_on()
        coord._client.connect.assert_awaited_once()

    async def test_turn_on_requests_refresh_on_success(self):
        entity, coord = _make_entity(connected=False)
        await entity.async_turn_on()
        coord.async_request_refresh.assert_awaited_once()

    async def test_turn_on_writes_state(self):
        entity, _ = _make_entity(connected=False)
        await entity.async_turn_on()
        entity.async_write_ha_state.assert_called_once()

    async def test_turn_on_does_not_raise_on_connect_failure(self):
        entity, coord = _make_entity(connected=False)
        coord._client.connect = AsyncMock(side_effect=Exception("BLE busy"))
        # Should not raise — logs warning and writes state
        await entity.async_turn_on()
        entity.async_write_ha_state.assert_called_once()

    def test_unique_id(self):
        entity, _ = _make_entity()
        assert entity._attr_unique_id == "AA:BB:CC:DD:EE:FF_ble_connection"
