# Nintendo Switch 2 Wake From Raspberry Pi Pico W

This project can be used to make a Raspberry Pi Pico W remotely wake up a Nintendo Switch 2 whenever an HTTP request is sent to the Pi.

The Raspberry Pi Pico W firmware built from this code runs a web server with the following endpoints:

- `/scan`: Makes the Pi scan for Bluetooth packets with a Nintendo marker. When seen, the packet payload (and associated metadata) is stored (overwriting any previous payload), and the Pi stops scanning. Note that the payload is stored in on-board flash, and as such will persist across rebooting the Pi.
- `/get-payload`: Prints the stored packet payload (and associated metadata) captured by `/scan` and broadcast by `/replay`.
- `/replay`: Broadcasts the packet most recently caught by `/scan`.

## Usage

Once the firmware is installed on the board (see **Installation** below):

1. Plug in or restart the controller
2. Remove the Nintendo Switch 2's right JoyCon (the one with the home button)
3. Determine the controller's IP address
4. Visit `http://<ip-address>/scan` in a browser to begin a scan
5. Press the right JoyCon's home (&#x2302;) button
6. Visit `http://<ip-address>/get-payload` to confirm capture. If an error is shown, go back to step (4).
7. Visit `http://<ip-address>/replay` to wake the switch
    - Note: You may need to visit this URL twice to wake the switch (if using a browser, simply refresh after a few seconds).

## Installation

### Dependencies

This step assumes a macOS development environment, but the process should work on Linux so long as the dependencies are installed with whatever package manager the environment uses.

```bash
brew install cmake python3
brew install --cask gcc-arm-embedded
```

### Build and Flash Firmware

This step builds a custom firmware consisting of [MicroPython](https://micropython.org) with an extra module (source code in this repository: `./modules/bthci/bthci.c`) added into the build to provide extra Bluetooth capabilities.

From within the folder containing this project and `README.md` file:

```bash
./setup.sh
cd micropython
make -C mpy-cross
cd ports/rp2
make BOARD=RPI_PICO_W "USER_C_MODULES=$(cd ../../../modules/bthci && pwd)" -j4

# Hold "BOOTSEL" while plugging the Pi into your machine.
# Then, copy the uf2 firmware onto the device. For example, on macOS:
cp ./build-RPI_PICO_W/firmware.uf2 /Volumes/RPI-RP2/
```


### Configure Firmware

Finally, configure the firmware. From within the folder containing this project and `README.md` file:

```bash
cp ./src/config.py.example ./src/config.py
# Edit ./src/config.py to include your Wi-Fi network's SSID and Password
```

Then configure the controller (assuming [uv](https://docs.astral.sh/uv/) is installed on the system):

```bash
uv tool install mpremote

mpremote connect auto fs cp src/config.py :config.py
mpremote connect auto fs cp src/main.py :main.py

# Optionally reboot the Pi and connect to it
mpremote connect auto reset
mpremote connect auto
```

At this point, use the controller as described in the **Usage** section above.

