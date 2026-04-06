"""Standalone BLE discovery and diagnostic script for Velit devices.

Run this script against real hardware to capture advertisement data,
probe the device's expected packet addresses, and confirm the protocol
behaves as documented.

Usage:
    python tools/discover.py [--address AA:BB:CC:DD:EE:FF]

Without --address: scans for all nearby Velit devices and prints their
full advertisement data. Useful for capturing manufacturer/service data
that may reveal device type (heater vs AC) without requiring user input.

With --address: briefly scans to capture advertisement data for the
target address, then connects and:
  1. Prints captured advertisement bytes (manufacturer ID, service UUIDs).
  2. Reads all GATT services and characteristics.
  3. Queries firmware version via JSON command (AC protocol).
  4. Subscribes to the notification characteristic (FFe1).
  5. Sends heater Query 1 (0x0A) and Query 2 (0x0B) with address candidates.
  6. If no heater responses, sends AC query packets (0x5A5A framing) for
     power, mode, temperature, fan speed, fault, and inlet temperature.
  7. Prints all raw notifications received throughout.

Hardware verification targets:
  - Capture advertisement bytes to determine device type differentiators
    (manufacturer ID, service UUIDs in advertisement vs GATT).
  - Confirm heater or AC protocol response structure against spec docs.
  - Determine which master/slave addresses the heater accepts.
  - Capture AC firmware version string.
  - Confirm AC two-way communication with 0x5A5A framed packets.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

# Allow running from the project root without installing the package.
sys.path.insert(0, ".")

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

# BLE advertisement local name prefixes used by known Velit heater firmware.
# AC units may advertise with different names (e.g. "LS Dis Server" observed
# on a 2000R unit). The service UUID filter below is more reliable.
_VELIT_NAME_PREFIXES = ("VELIT", "VLIT", "D30")

# BEKEN Corp manufacturer ID (0x585A = 22618), present in known Velit heater
# advertisements. Whether AC units share this ID is unconfirmed.
_VELIT_MANUFACTURER_ID = 22618

# BLE service UUID shared by all known Velit devices (heater and AC).
# Used as a reliable advertisement filter that is independent of local name
# and manufacturer data.
_VELIT_SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"

# Characteristic UUIDs (same on heater and AC).
_UUID_READ_NOTIFY = "0000ffe1-0000-1000-8000-00805f9b34fb"
_UUID_WRITE = "0000ffe2-0000-1000-8000-00805f9b34fb"

# Heater address candidates. The heater protocol uses 4-byte master/slave
# addresses unrelated to BLE MAC addresses; their origin is unknown.
_MASTER_CANDIDATES = [
    bytes([0x00, 0x00, 0x00, 0x01]),  # protocol document example
    bytes([0x00, 0x00, 0x00, 0x00]),
    bytes([0xFF, 0xFF, 0xFF, 0xFF]),
]
_SLAVE_CANDIDATES = [
    bytes([0x00, 0x00, 0x00, 0x2D]),  # protocol document example (45)
    bytes([0x00, 0x00, 0x00, 0x01]),
    bytes([0x00, 0x00, 0x00, 0x00]),
    bytes([0xFF, 0xFF, 0xFF, 0xFF]),
]

_HEATER_QUERY_1 = 0x0A  # Query Command 1 — machine state, temps, fan RPM, etc.
_HEATER_QUERY_2 = 0x0B  # Query Command 2 — inlet/casing/outlet temps, voltage

# AC product code used in all 0x5A5A framed packets (per V1.01 spec example).
_AC_PRODUCT_CODE = 0x01

# AC function codes to query.
_AC_QUERIES = [
    (0x01, "power state"),
    (0x02, "operation mode"),
    (0x03, "temperature"),
    (0x04, "fan speed"),
    (0x07, "inlet air temperature"),
    (0x0B, "fault info"),
    (0x10, "swing"),
]

_SCAN_TIMEOUT = 10.0   # seconds for open scan
_ADV_CAPTURE_TIMEOUT = 8.0  # seconds to scan for a specific address before connecting


def _is_velit(device: BLEDevice, adv: AdvertisementData) -> bool:
    name = adv.local_name or device.name or ""
    if name.startswith(_VELIT_NAME_PREFIXES):
        return True
    if _VELIT_MANUFACTURER_ID in adv.manufacturer_data:
        return True
    return _VELIT_SERVICE_UUID in (adv.service_uuids or [])


def _heater_checksum(payload: bytes) -> bytes:
    """2-byte LRC2: sum of all payload bytes, big-endian."""
    total = sum(payload) & 0xFFFF
    return bytes([total >> 8, total & 0xFF])


def _build_heater_packet(master: bytes, slave: bytes, func: int, data: bytes) -> bytes:
    length = 4 + 4 + 1 + len(data) + 2
    header = bytes([0x55, length]) + master + slave + bytes([func]) + data
    return header + _heater_checksum(header)


def _ac_checksum(payload: bytes) -> int:
    """1-byte checksum: low byte of the sum of all bytes from header through data."""
    return sum(payload) & 0xFF


def _build_ac_packet(product: int, func: int, data: bytes) -> bytes:
    # Length = header (2) + product (1) + func (1) + data + checksum (1).
    # The length field itself is not counted.
    length = 2 + 1 + 1 + len(data) + 1
    body = bytes([0x5A, 0x5A, length, product, func]) + data
    checksum = _ac_checksum(body)
    return body + bytes([checksum, 0x0D, 0x0A])


def _print_adv(device: BLEDevice, adv: AdvertisementData) -> None:
    print(f"\nDevice:   {device.address}")
    print(f"  Name:   {adv.local_name or device.name or '(none)'}")
    print(f"  RSSI:   {adv.rssi} dBm")
    if adv.manufacturer_data:
        for company_id, payload in adv.manufacturer_data.items():
            print(f"  Manufacturer data (0x{company_id:04X} / {company_id}): {payload.hex(' ')}")
    else:
        print("  Manufacturer data: (none)")
    if adv.service_uuids:
        for uuid in adv.service_uuids:
            print(f"  Service UUID: {uuid}")
    else:
        print("  Service UUIDs in advertisement: (none)")
    if adv.service_data:
        for uuid, payload in adv.service_data.items():
            print(f"  Service data ({uuid}): {payload.hex(' ')}")


# ---------------------------------------------------------------------------
# Scan mode
# ---------------------------------------------------------------------------


async def scan() -> None:
    """Scan for Velit devices and print full advertisement data."""
    print(
        f"Scanning {_SCAN_TIMEOUT:.0f}s for Velit devices "
        f"(name prefix, manufacturer ID {_VELIT_MANUFACTURER_ID}, "
        f"or service UUID {_VELIT_SERVICE_UUID})..."
    )
    found: list[tuple[BLEDevice, AdvertisementData]] = []
    seen: set[str] = set()

    def callback(device: BLEDevice, adv: AdvertisementData) -> None:
        if _is_velit(device, adv) and device.address not in seen:
            seen.add(device.address)
            found.append((device, adv))
            _print_adv(device, adv)

    async with BleakScanner(detection_callback=callback):
        await asyncio.sleep(_SCAN_TIMEOUT)

    print(f"\nScan complete. Found {len(found)} Velit device(s).")
    if found:
        print("\nTo probe a device, run:")
        for device, _ in found:
            print(f"  python tools/discover.py --address {device.address}")


# ---------------------------------------------------------------------------
# Probe mode
# ---------------------------------------------------------------------------


async def _capture_advertisement(address: str) -> tuple[BLEDevice, AdvertisementData] | None:
    """Scan briefly to capture advertisement data for a specific address."""
    print(f"Scanning {_ADV_CAPTURE_TIMEOUT:.0f}s to capture advertisement for {address}...")
    result: tuple[BLEDevice, AdvertisementData] | None = None
    target = address.upper()
    found_event = asyncio.Event()

    def callback(device: BLEDevice, adv: AdvertisementData) -> None:
        nonlocal result
        if device.address.upper() == target and result is None:
            result = (device, adv)
            found_event.set()

    async with BleakScanner(detection_callback=callback):
        try:
            await asyncio.wait_for(found_event.wait(), timeout=_ADV_CAPTURE_TIMEOUT)
        except asyncio.TimeoutError:
            pass

    return result


async def probe(address: str) -> None:
    """Connect to a device and run heater and AC diagnostic probes."""
    notifications: list[bytes] = []

    def on_notify(_char, data: bytearray) -> None:
        raw = bytes(data)
        notifications.append(raw)
        print(f"  << notification: {raw.hex(' ')}")

    # Capture advertisement before connecting.
    adv_result = await _capture_advertisement(address)
    if adv_result:
        print("\nAdvertisement captured:")
        _print_adv(*adv_result)
    else:
        print(f"\nNo advertisement seen for {address} within {_ADV_CAPTURE_TIMEOUT:.0f}s.")
        print("  (device may not be actively advertising — proceeding to connect anyway)")

    print(f"\nConnecting to {address}...")
    async with BleakClient(address) as client:
        print("Connected.")

        # List services and characteristics.
        print("\nGATT services:")
        for service in client.services:
            print(f"  Service: {service.uuid}")
            for char in service.characteristics:
                props = ", ".join(char.properties)
                print(f"    Char: {char.uuid}  [{props}]")

        # Attempt firmware version query via JSON (AC OTA protocol).
        print("\nQuerying firmware version (JSON command)...")
        try:
            info_cmd = json.dumps({"cmd": "info"}).encode()
            await client.write_gatt_char(_UUID_WRITE, info_cmd, response=False)
            await asyncio.sleep(1.0)
            print("  (any JSON response will appear as a notification above)")
        except Exception as exc:
            print(f"  firmware query error: {exc}")

        # Subscribe to notifications.
        await client.start_notify(_UUID_READ_NOTIFY, on_notify)
        print(f"\nSubscribed to notifications on {_UUID_READ_NOTIFY}")

        # --- Heater probe ---
        heater_notification_start = len(notifications)
        print("\nProbing heater protocol (0x55 framing, func 0x0A / 0x0B)...")
        print("  Heater devices will respond; AC devices will not.")

        for master in _MASTER_CANDIDATES:
            for slave in _SLAVE_CANDIDATES:
                for func in (_HEATER_QUERY_1, _HEATER_QUERY_2):
                    pkt = _build_heater_packet(master, slave, func, bytes([0x00]))
                    print(
                        f"\n  >> master={master.hex()} slave={slave.hex()} "
                        f"func=0x{func:02X}  packet: {pkt.hex(' ')}"
                    )
                    try:
                        await client.write_gatt_char(_UUID_WRITE, pkt, response=True)
                    except Exception as exc:
                        print(f"     write error: {exc}")
                    await asyncio.sleep(0.5)

        heater_notifications = len(notifications) - heater_notification_start

        # --- AC probe ---
        ac_notification_start = len(notifications)

        if heater_notifications == 0:
            print("\nNo heater responses — probing AC protocol (0x5A5A framing)...")
        else:
            print(f"\n{heater_notifications} heater response(s) received. Also probing AC protocol...")

        for func, description in _AC_QUERIES:
            pkt = _build_ac_packet(_AC_PRODUCT_CODE, func, bytes([0x00]))
            print(f"\n  >> AC query 0x{func:02X} ({description})  packet: {pkt.hex(' ')}")
            try:
                await client.write_gatt_char(_UUID_WRITE, pkt, response=False)
            except Exception as exc:
                print(f"     write error: {exc}")
            await asyncio.sleep(0.6)  # AC spec: 400ms minimum between commands

        ac_notifications = len(notifications) - ac_notification_start

        # Collect any remaining unsolicited notifications.
        print("\nListening 5s for any further notifications...")
        await asyncio.sleep(5.0)

        await client.stop_notify(_UUID_READ_NOTIFY)

    print(f"\nProbe complete.")
    print(f"  Heater protocol notifications: {heater_notifications}")
    print(f"  AC protocol notifications:     {ac_notifications}")
    print(f"  Total:                         {len(notifications)}")

    if len(notifications) == 0:
        print(
            "\nNo notifications received from either protocol. Possible causes:\n"
            "  - Device requires pairing before responding\n"
            "  - Characteristic UUID differs on this firmware version\n"
            "  - Product code 0x01 not accepted by this AC model\n"
            "  - Device was not in a responsive state (check power)"
        )
    elif heater_notifications > 0 and ac_notifications == 0:
        print("\nHeater protocol confirmed. Device is a Velit heater.")
    elif ac_notifications > 0 and heater_notifications == 0:
        print("\nAC protocol confirmed. Device is a Velit AC unit.")
    else:
        print("\nBoth protocols received responses — unexpected. Review raw output above.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Velit BLE discovery and diagnostic tool")
    parser.add_argument(
        "--address",
        metavar="ADDR",
        help="BLE address to probe directly (captures advertisement, then connects)",
    )
    args = parser.parse_args()

    if args.address:
        asyncio.run(probe(args.address))
    else:
        asyncio.run(scan())


if __name__ == "__main__":
    main()
