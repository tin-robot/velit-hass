"""Heater BLE packet builder and response parser.

Protocol: Velit Air Heater Communication Protocol V1.02.
This module handles packet construction and parsing only.
BLE connection management is implemented separately.

Packet structure (command, master to slave):
  [0x55][length][master 4B][slave 4B][func][data N][checksum 2B]

Packet structure (response, slave to master):
  [0xAA][length][master 4B][slave 4B][SF 2B][func][data N][checksum 2B]

Checksum: unsigned 16-bit sum of all bytes from start flag through data,
high byte first. Verified against 11 of 12 protocol examples — the shutdown
command example (func 0x02) appears to contain a typo in the source document
and does not match the formula. Hardware verification required.

Open question: the 4-byte master/slave addresses used in the protocol are not
the same as BLE MAC addresses (which are 6 bytes). How these addresses are
assigned or discovered is not yet known. Needs hardware investigation.
"""

from __future__ import annotations

import logging

_LOGGER = logging.getLogger(__name__)

# Packet framing constants
_START_CMD = 0x55
_START_RSP = 0xAA
_MFG_CODE = bytes([0x53, 0x46])  # "SF" — present in every response

# Minimum valid response length: AA + len + master(4) + slave(4) + SF(2) + func + data(>=1) + cksum(2)
_MIN_RESPONSE_LEN = 16


def build_command(
    master_addr: bytes,
    slave_addr: bytes,
    func: int,
    data: bytes,
) -> bytes:
    """Build a complete heater command packet ready to write to the BLE characteristic.

    Args:
        master_addr: 4-byte master address.
        slave_addr:  4-byte slave device address.
        func:        1-byte function code.
        data:        Command payload bytes (variable length).

    Returns:
        Complete packet as bytes including start flag and checksum.

    Raises:
        ValueError: If address lengths are not 4 bytes.
    """
    if len(master_addr) != 4 or len(slave_addr) != 4:
        raise ValueError("master_addr and slave_addr must each be 4 bytes")

    # Length = bytes after the length field: master(4) + slave(4) + func(1) + data(N) + checksum(2)
    length = 4 + 4 + 1 + len(data) + 2

    header = bytes([_START_CMD, length]) + master_addr + slave_addr + bytes([func]) + data
    checksum = _heater_checksum(header)
    return header + checksum


def parse_response(raw: bytes) -> dict | None:
    """Parse a heater response packet.

    Validates start flag, minimum length, manufacturer code, and checksum.

    Returns a dict with keys: func, data, master_addr, slave_addr.
    Returns None if the packet is invalid.
    """
    if len(raw) < _MIN_RESPONSE_LEN:
        _LOGGER.debug("Response too short: %d bytes", len(raw))
        return None

    if raw[0] != _START_RSP:
        _LOGGER.debug("Unexpected start byte: 0x%02X", raw[0])
        return None

    # Manufacturer code at bytes 10–11 (after AA + len + master(4) + slave(4))
    if raw[10:12] != _MFG_CODE:
        _LOGGER.debug("Manufacturer code mismatch: %s", raw[10:12].hex())
        return None

    if not _validate_response_checksum(raw):
        _LOGGER.debug("Checksum mismatch on response: %s", raw.hex())
        return None

    master_addr = raw[2:6]
    slave_addr = raw[6:10]
    func = raw[12]
    # Data sits between func byte and the 2-byte checksum at the end
    data = raw[13:-2]

    return {
        "func": func,
        "data": data,
        "master_addr": master_addr,
        "slave_addr": slave_addr,
    }


def _heater_checksum(payload: bytes) -> bytes:
    """Compute the 2-byte LRC2 checksum for a heater packet.

    Sum of all bytes in payload (start flag through data), returned
    as 2 bytes big-endian (high byte first).
    """
    total = sum(payload) & 0xFFFF
    return bytes([total >> 8, total & 0xFF])


def _validate_response_checksum(raw: bytes) -> bool:
    """Return True if the response checksum is correct.

    Checksum covers all bytes from start flag through data (everything
    except the final 2 checksum bytes).
    """
    expected = _heater_checksum(raw[:-2])
    return raw[-2:] == expected
