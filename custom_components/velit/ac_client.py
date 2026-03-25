"""AC BLE packet builder and response parser.

Protocol: Velit Air Conditioner Communication Protocol V1.01.
This module handles packet construction and parsing only.
BLE connection management is implemented separately.

Packet structure (command, app to AC):
  [0x5A][0x5A][length][product_code][func][data N][checksum 1B][0x0D][0x0A]

Packet structure (response, AC to app):
  [0x5A][0x5A][length][product_code][func][data N][checksum 1B][0x0D][0x0A]

Checksum: sum of all bytes from frame header through data, low byte only.
Verified against the single known example in the protocol document.
Additional examples needed for full confidence — hardware verification required.

Length field: based on the single documented example (1 data byte, length=6),
the length value appears to equal len(data) + 5. This is a theory and requires
hardware verification with multi-byte data payloads.

Note: command transmission interval must be at least 400ms.
On no response within 3 seconds, retry once. After 3 total failures,
mark the device as unavailable.
"""

from __future__ import annotations

import logging

_LOGGER = logging.getLogger(__name__)

# Packet framing
_HEADER = bytes([0x5A, 0x5A])
_TERMINATOR = bytes([0x0D, 0x0A])

# Product code used in the documented example. The protocol does not
# explicitly document all valid product code values — needs verification.
DEFAULT_PRODUCT_CODE = 0x01

# Minimum valid response: header(2) + len(1) + product(1) + func(1) + data(>=1) + cksum(1) + term(2)
_MIN_RESPONSE_LEN = 9


def build_command(func: int, data: bytes, product_code: int = DEFAULT_PRODUCT_CODE) -> bytes:
    """Build a complete AC command packet ready to write to the BLE characteristic.

    Args:
        func:         1-byte function code.
        data:         Command payload bytes (variable length).
        product_code: 1-byte product identifier (default 0x01 per protocol example).

    Returns:
        Complete packet as bytes including header, checksum, and terminator.
    """
    # Length theory: len(data) + 5, based on the single documented example.
    # The example has 1 data byte and length=6: 1 + 5 = 6.
    length = len(data) + 5

    payload = _HEADER + bytes([length, product_code, func]) + data
    checksum = _ac_checksum(payload)
    return payload + bytes([checksum]) + _TERMINATOR


def parse_response(raw: bytes) -> dict | None:
    """Parse an AC response packet.

    Validates header, terminator, minimum length, and checksum.

    Returns a dict with keys: func, data, product_code.
    Returns None if the packet is invalid.
    """
    if len(raw) < _MIN_RESPONSE_LEN:
        _LOGGER.debug("Response too short: %d bytes", len(raw))
        return None

    if raw[:2] != _HEADER:
        _LOGGER.debug("Unexpected header: %s", raw[:2].hex())
        return None

    if raw[-2:] != _TERMINATOR:
        _LOGGER.debug("Missing terminator: %s", raw[-2:].hex())
        return None

    if not _validate_response_checksum(raw):
        _LOGGER.debug("Checksum mismatch on response: %s", raw.hex())
        return None

    product_code = raw[3]
    func = raw[4]
    # Data sits between func byte and checksum+terminator at the end
    data = raw[5:-3]

    return {
        "func": func,
        "data": data,
        "product_code": product_code,
    }


def _ac_checksum(payload: bytes) -> int:
    """Compute the 1-byte checksum for an AC packet.

    Sum of all bytes in payload (header through data), low byte only.
    """
    return sum(payload) & 0xFF


def _validate_response_checksum(raw: bytes) -> bool:
    """Return True if the response checksum is correct.

    Checksum covers all bytes from header through data (raw[:-3]),
    excluding the checksum byte and 0x0D 0x0A terminator.
    """
    expected = _ac_checksum(raw[:-3])
    return raw[-3] == expected
