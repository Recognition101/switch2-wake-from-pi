add_library(usermod_bthci INTERFACE)
target_sources(usermod_bthci INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/bthci.c
)
target_include_directories(usermod_bthci INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}
)
target_include_directories(usermod_bthci INTERFACE
    ${MICROPY_DIR}/lib/btstack/src
)
target_link_libraries(usermod INTERFACE usermod_bthci)
