"""Shared packet utilities for Velit heater and AC protocols."""

from __future__ import annotations

from .const import (
    AC_MAX_TEMP_C,
    AC_MIN_TEMP_C,
    HEATER_MAX_TEMP_C,
    HEATER_MIN_TEMP_C,
)


def celsius_to_hex(temp_c: int) -> int:
    """Return the hex value transmitted for a Celsius temperature.

    Both devices transmit the raw integer degree value as a single hex byte.
    Formula: F = 1.8 * C + 32 (used when transmitting Fahrenheit instead).
    """
    return temp_c


def fahrenheit_to_hex(temp_f: int) -> int:
    """Return the hex value transmitted for a Fahrenheit temperature."""
    return temp_f


def hex_to_celsius(value: int) -> int:
    """Convert a received hex temperature value to Celsius."""
    return value


def hex_to_fahrenheit(value: int) -> int:
    """Convert a received hex temperature value to Fahrenheit."""
    return value


def celsius_to_fahrenheit(temp_c: float) -> float:
    """Convert Celsius to Fahrenheit using the protocol formula."""
    return 1.8 * temp_c + 32


def fahrenheit_to_celsius(temp_f: float) -> float:
    """Convert Fahrenheit to Celsius."""
    return (temp_f - 32) / 1.8


def is_valid_heater_temp_c(temp_c: int) -> bool:
    """Return True if the temperature is within the heater's Celsius range."""
    return HEATER_MIN_TEMP_C <= temp_c <= HEATER_MAX_TEMP_C


def is_valid_heater_temp_f(temp_f: int) -> bool:
    """Return True if the temperature is within the heater's Fahrenheit range.

    F range per protocol: 61–86°F (hex 0x3D–0x56).
    """
    return 61 <= temp_f <= 86


def is_valid_ac_temp_c(temp_c: int) -> bool:
    """Return True if the temperature is within the AC's Celsius range."""
    return AC_MIN_TEMP_C <= temp_c <= AC_MAX_TEMP_C


def is_valid_ac_temp_f(temp_f: int) -> bool:
    """Return True if the temperature is within the AC's Fahrenheit range.

    F range per protocol: 61–86°F (hex 0x3D–0x56).
    """
    return 61 <= temp_f <= 86
