#include <string.h>

#include "py/runtime.h"
#include "py/obj.h"
#include "py/mperrno.h"
#include "py/mphal.h"

// For hci_send_cmd() / bd_addr_t / gap_local_bd_addr()
#include "hci.h"
#include "gap.h"

#define BTHCI_HCI_TIMEOUT_MS 1000

/**
 * The "Write BD_ADDR" command code is `0xFC01` for Broadcom/Cypress/Infineon,
 * and "B" indicates the MAC address is passed as little-endian.
 * @see https://github.com/FreeTHX/pywakepsx-on-bt/blob/main/pywakepsx_on_bt/strategies/README.md
 */
static const hci_cmd_t bcm_write_bd_addr = { 0xFC01, "B" };

/** Runs the MicroPython event loop until HCI is ready for a new command. */
static void wait_for_hci_ready(void) {
    mp_uint_t start = mp_hal_ticks_ms();
    while (!hci_can_send_command_packet_now()) {
        if (mp_hal_ticks_ms() - start > BTHCI_HCI_TIMEOUT_MS) {
            mp_raise_OSError(MP_ETIMEDOUT);
        }
        mp_event_wait_ms(1);
    }
}

/**
 * Sets the Bluetooth Device (MAC) Address (bd_addr) of this device to a given
 * address.
 * @param addr_obj the address to use for future BT commands
 */
static mp_obj_t bthci_set_bd_addr(mp_obj_t addr_obj) {
    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(addr_obj, &bufinfo, MP_BUFFER_READ);
    if (bufinfo.len != 6) {
        mp_raise_ValueError(MP_ERROR_TEXT("address must be 6 bytes"));
    }
    if (hci_get_state() != HCI_STATE_WORKING) {
        mp_raise_msg(&mp_type_OSError, MP_ERROR_TEXT(
            "`set_bd_addr` Error: Call `bluetooth.BLE().active(True)` first."
        ));
    }

    bd_addr_t addr;
    memcpy(addr, bufinfo.buf, 6);

    wait_for_hci_ready();
    hci_send_cmd(&bcm_write_bd_addr, addr);

    // Wait until HCI updates the address, then confirm it was adopted.
    wait_for_hci_ready();
    hci_send_cmd(&hci_read_bd_addr);

    mp_uint_t start = mp_hal_ticks_ms();
    while (true) {
        bd_addr_t current;
        gap_local_bd_addr(current);
        if (memcmp(current, addr, 6) == 0) {
            break;
        }
        if (mp_hal_ticks_ms() - start > BTHCI_HCI_TIMEOUT_MS) {
            mp_raise_msg(&mp_type_OSError, MP_ERROR_TEXT(
                "`set_bd_addr` Error: Controller did not adopt given BD_ADDR"
            ));
        }
        mp_event_wait_ms(1);
    }

    return mp_const_none;
}

// Expose the module and provided functions
static MP_DEFINE_CONST_FUN_OBJ_1(bthci_set_bd_addr_obj, bthci_set_bd_addr);

static const mp_rom_map_elem_t bthci_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_bthci) },
    { MP_ROM_QSTR(MP_QSTR_set_bd_addr), MP_ROM_PTR(&bthci_set_bd_addr_obj) },
};
static MP_DEFINE_CONST_DICT(bthci_module_globals, bthci_module_globals_table);

const mp_obj_module_t bthci_user_cmodule = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&bthci_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_bthci, bthci_user_cmodule);
