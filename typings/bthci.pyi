# Stub for functions provided by ./modules/bthci/bthci.c
def set_bd_addr(addr: bytes, /) -> None:
    """Set the Bluetooth controller's public address (BD_ADDR).

    Args:
        addr (bytes): MAC address (ex: express AA:BB:... with b"\\xAA\\xBB...")

    Raises:
        ValueError: `addr` isn't 6 bytes
        OSError: Inactive BT or the controller's MAC did not become `addr`
    """
    ...
