#!/usr/bin/env bash
set -e

# Command Line Arg Parsing

POSITIONAL_ARGS=()
while [[ $# -gt 0 ]]; do
    case $1 in
        -c|--clean) CLEAN=1; shift;;
        -h|--help)  HELP=1; shift;;
        -*|--*)     echo "Unknown option $1\n"; HELP=1; shift;;
        *)          POSITIONAL_ARGS+=("$1"); shift;;
    esac
done

# Help Message

if [ $HELP ]; then
    echo "
Gets this project ready for development by installing external dependencies.
Dependencies are only installed if absent (or if --clean is passed).

OPTIONS:
    -c, --clean  Deletes/replaces existing dependencies.
    -h, --help   Display this message and exit.
    "
    exit 0
fi

# Clean folders

if [ $CLEAN ]; then
    rm -rf ./.stubs
    rm -rf ./micropython
fi

# Install Stubs

if [ ! -d "./.stubs" ]; then
    mkdir ./.stubs
    uv pip install --target .stubs "micropython-rp2-rpi_pico_w-stubs==1.29.*"
fi

# Install MicroPython (for custom firmware build)

if [ ! -d "./micropython" ]; then
    git clone --depth=1 https://github.com/micropython/micropython.git
    cd micropython
    git submodule update --init --depth 1 lib/pico-sdk lib/cyw43-driver lib/lwip \
        lib/btstack lib/mbedtls lib/tinyusb lib/micropython-lib
    cd ..
fi
