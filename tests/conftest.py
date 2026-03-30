# Shared fixtures for the Velit integration test suite.

from unittest.mock import patch

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integration loading for all tests in this suite."""


@pytest.fixture(autouse=True)
def mock_bluetooth_adapters() -> None:
    """Prevent the bluetooth component from trying to access BlueZ/dbus.

    The bluetooth dependency in manifest.json causes HA to set up the bluetooth
    component during config flow tests. On non-Linux systems (macOS, CI) the
    adapter history call fails because BlueZ/dbus is unavailable. Patching it
    to return empty state lets the component set up cleanly without hardware.
    """
    with patch(
        "homeassistant.components.bluetooth.util.async_load_history_from_system",
        return_value=({}, {}),
    ):
        yield
