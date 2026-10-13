import time
import os
import json
import binascii
import network
import bluetooth
import asyncio
import micropython
from micropython import const

import bthci
from config import WIFI_SSID, WIFI_PASSWORD


# --- Type Checking ---

TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import Any, Literal, TypedDict

    class Payload(TypedDict):
        body: bytes    # raw advertising packet bytes
        addr: bytes    # source MAC address, 6 bytes, reading order
        addr_type: int # 0 = public, 1 = random
        adv_type: int  # PDU type, one of _ADV_*


# --- Constants ---

BURST_MS = 2000                  # `/replay` duration (milliseconds)
ADV_INTERVAL_US = 30_000         # `/replay` advertisement (microseconds)
SCAN_DURATION_MS = 5 * 60 * 1000 # `/scan` runs a scan this long (milliseconds)
SCAN_INTERVAL_US = 60_000        # `/scan` time between checks (microseconds)
SCAN_WINDOW_US = 60_000          # `/scan` check duration (microseconds)
PAYLOAD_FILE = "/payload.json"

_IRQ_SCAN_RESULT = const(5)
_IRQ_SCAN_DONE = const(6)
_ADDR_TYPE_PUBLIC = const(0)
_ADV_IND = const(0)
_ADV_SCAN_IND = const(2)
_ADV_NONCONN_IND = const(3)


# --- State ---

_ble = bluetooth.BLE()  # radio stays off until main() calls .active(True)
_advertising: bool = False
_scanning: bool = False
_payload: "Payload | None" = None


# --- Functions ---

def _hex(data: bytes, delimiter: str = " ") -> str:
    """String-formats arbitrary hex data.

    Args:
        data (bytes): the bytes to format
        delimiter=" " (string): the delimiter to print between each byte

    Returns:
        string: the string representing `data`
    """
    return delimiter.join("%02X" % b for b in data)


def payload_json(payload: "Payload") -> str:
    """String-formats payload data (hex packet data and associated metadata).

    Args:
        payload (Payload): the payload to format

    Returns:
        string: the string representation of `payload`
    """
    return json.dumps({
        "body": binascii.hexlify(payload["body"]).decode(),
        "addr": binascii.hexlify(payload["addr"]).decode(),
        "addr_type": payload["addr_type"],
        "adv_type": payload["adv_type"],
    })


def save_payload(payload: "Payload") -> None:
    """Saves payload data to the local filesystem.

    Args:
        payload (Payload): the payload to save
    """
    tmp = PAYLOAD_FILE + ".tmp"
    try:
        with open(tmp, "w") as f:
            f.write(payload_json(payload)) # write is non-atomic
        os.rename(tmp, PAYLOAD_FILE) # rename is atomic
        print("[storage][INFO] saved payload to: %s" % PAYLOAD_FILE)
    except OSError as e:
        print("[storage][ERROR] could not save payload :: %r" % e)


def load_payload() -> None:
    """Reads payload data from the local filesystem.

    Globals:
        _payload (Payload): payload data read from storage is stored here
    """
    global _payload
    try:
        with open(PAYLOAD_FILE) as f:
            saved = json.load(f)
        payload: "Payload" = {
            "body": binascii.unhexlify(saved["body"]),
            "addr": binascii.unhexlify(saved["addr"]),
            "addr_type": int(saved["addr_type"]),
            "adv_type": int(saved["adv_type"]),
        }
    except OSError:
        print("[storage][INFO] no payload in storage to load")
        return
    except (ValueError, KeyError, TypeError) as e:
        print("[storage][ERROR] cannot read: %s :: %r" % (PAYLOAD_FILE, e))
        return
    if len(payload["addr"]) != 6 or not 0 < len(payload["body"]) <= 31:
        print("[storage][ERROR] bad address or payload in: %s" % PAYLOAD_FILE)
        return
    _payload = payload
    print("[storage][INFO] loaded payload: %s" % payload_json(_payload))


def _is_from_nintendo(adv_data: "bytes | memoryview") -> "Literal['CID', 'VID'] | None":
    """Gets whether or not a packet contains identifiers from Nintendo.

    Args:
        adv_data (memoryview): the packet data to scan for identifiers

    Returns:
        "CID" | "VID" | None: the kind of Nintendo-hex match, or `None` found
    """
    for i in range(len(adv_data) - 1):
        if adv_data[i] == 0x53 and adv_data[i + 1] == 0x05: # Company ID 0x0553
            return "CID"
        if adv_data[i] == 0x7E and adv_data[i + 1] == 0x05: # VID 0x057E
            return "VID"
    return None


def _on_capture(payload: "Payload") -> None:
    """Event handler that runs upon capturing a Nintendo-matching packet.

    Args:
        payload (Payload): the payload that was captured
    Globals:
        _ble (BLE): the Bluetooth LE connection
    """
    _ble.gap_scan(None)  # ty: ignore[invalid-argument-type]
    save_payload(payload)


def _bt_irq(event: int, data: "tuple[Any, ...]") -> None:
    """Event handler that runs on a Bluetooth interrupt request (IRQ).

    On scan result events, it stores Nintendo-matching payloads.
    On scan ending events, it cleans up.

    Args:
        event (int): the event type enumeration value to process
        data (
            Tuple[int, int, memoryview]
            | Tuple[int, int]
            | Tuple[int, int, int, int, memoryview]
        ): the Bluetooth data carried by the event

    Globals:
        _scanning (boolean): flags whether we are still scanning or not
        _payload (Payload): the payload data found
    """
    global _scanning, _payload
    if event == _IRQ_SCAN_RESULT:
        addr_type: int
        addr: memoryview
        adv_type: int
        rssi: int
        adv_data: memoryview
        addr_type, addr, adv_type, rssi, adv_data = data
        if not _scanning:
            return
        if adv_type not in (_ADV_IND, _ADV_SCAN_IND, _ADV_NONCONN_IND):
            return
        marker = _is_from_nintendo(adv_data)
        if marker is None:
            return
        _scanning = False
        _payload = {
            "body": bytes(adv_data),
            "addr": bytes(addr),
            "addr_type": addr_type,
            "adv_type": adv_type,
        }
        print("[scan][INFO] captured: RSSI=%d Marker=%s Payload=%s" %
            (rssi, marker, payload_json(_payload))
        )
        micropython.schedule(_on_capture, _payload)
    elif event == _IRQ_SCAN_DONE:
        _scanning = False
        print("[scan][INFO] scan stopped")


async def fire_replay_burst(payload: "Payload") -> None:
    """Replays a given payload.

    Args:
        payload (Payload): the payload to broadcast
    Globals:
        _ble (BLE): the Bluetooth LE connection
    """
    global _advertising
    if _advertising:
        print("[replay][INFO] burst already in flight, ignoring request")
        return
    _advertising = True
    try:
        if payload["addr_type"] != _ADDR_TYPE_PUBLIC:
            print("[replay][WARN] payload MAC is not public")

        bthci.set_bd_addr(payload["addr"])
        print("[replay][INFO] MAC: %s" % _hex(_ble.config("mac")[1], ":"))
        _ble.gap_advertise(
            ADV_INTERVAL_US,
            payload["body"],
            connectable = (payload["adv_type"] == _ADV_IND)
        )
        print("[replay][INFO] advertising for %d ms: %s" %
            (BURST_MS, payload_json(payload))
        )
        await asyncio.sleep_ms(BURST_MS)  # ty: ignore[unresolved-attribute]
        _ble.gap_advertise(None)  # ty: ignore[invalid-argument-type]
        print("[replay][INFO] advertising done")
    finally:
        _advertising = False


def _http_response(
    status_line: bytes, body_bytes: bytes, content_type: bytes = b"text/plain"
) -> bytes:
    """Creates an HTTP response string.

    Args:
        status_line (bytes): the HTTP-code/description line (ex: b"200 OK")
        body_bytes (bytes): the HTTP body text
        content_type="text/plain" (bytes): the MIME type of the content

    Returns:
        bytes: the HTTP response text
    """
    return (
        b"HTTP/1.1 " + status_line + b"\r\n"
        b"Access-Control-Allow-Origin: *\r\n"
        b"Content-Type: " + content_type + b"\r\n"
        b"Content-Length: " + str(len(body_bytes)).encode() + b"\r\n"
        b"Connection: close\r\n"
        b"\r\n" + body_bytes
    )


async def handle_client(
    reader: "asyncio.StreamReader", writer: "asyncio.StreamWriter"
) -> None:
    """Handles an HTTP request.

    Args:
        reader (StreamReader): the HTTP request data
        writer (StreamWriter): the stream to write the response text to

    Globals:
        _scanning (boolean): flags whether we are scanning or not
        _ble (BLE): the Bluetooth LE connection
    """
    global _scanning

    request_line = await reader.readline()

    while True:
        line = await reader.readline()
        if line in (b"\r\n", b""):
            break

    parts = request_line.split()
    method = parts[0]
    path = parts[1] if len(parts) >= 2 else b""
    path = path.split(b"?", 1)[0]

    if method == b"POST" and path == b"/scan":
        _scanning = True
        _ble.gap_scan(SCAN_DURATION_MS, SCAN_INTERVAL_US, SCAN_WINDOW_US, False)
        print("[scan][INFO] scanning (%d ms)" % SCAN_DURATION_MS)
        response = _http_response(b"200 OK", b"scanning\n")
    elif method == b"GET" and path == b"/get-payload":
        if _payload is None:
            response = _http_response(
                b"200 OK",
                b"{ \"error\": \"No payload captured.\" }",
                b"application/json"
            )
        else:
            body = payload_json(_payload).encode()
            response = _http_response(b"200 OK", body, b"application/json")
    elif method == b"POST" and path == b"/replay":
        if _payload is None:
            body = b"no payload yet\n"
        else:
            asyncio.create_task(fire_replay_burst(_payload))
            body = b"replaying: " + _hex(_payload["body"]).encode() + b"\n"
        response = _http_response(b"200 OK", body)
    else:
        response = _http_response(b"404 Not Found", b"404 Not Found")

    writer.write(response)
    await writer.drain()
    writer.close()
    await writer.wait_closed()


async def main() -> None:
    """The program entry point.

    Globals:
        _ble (BLE): the Bluetooth LE connection
    """
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)
    print("[main][INFO] Wi-Fi connecting to SSID '%s'..." % WIFI_SSID)
    start = time.ticks_ms()  # ty: ignore[unresolved-attribute]
    while not wlan.isconnected():
        if time.ticks_diff(time.ticks_ms(), start) > 30_000:  # ty: ignore[unresolved-attribute]
            raise RuntimeError("Wi-Fi connect timed out")
        time.sleep_ms(200)  # ty: ignore[unresolved-attribute]
    print("[main][INFO] Wi-Fi connected, IP:", wlan.ifconfig()[0])

    load_payload()

    _ble.irq(_bt_irq)
    _ble.active(True)
    print("[main][INFO] Device BT MAC: %s" % _hex(_ble.config("mac")[1], ":"))

    await asyncio.start_server(handle_client, "0.0.0.0", 80)
    print("[main][INFO] HTTP server listening on port 80")
    print("[main][INFO] routes: POST /scan, GET /get-payload, POST /replay")
    while True:
        await asyncio.sleep(3600)


asyncio.run(main())
