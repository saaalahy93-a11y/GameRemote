cmake_minimum_required(VERSION 3.22)
project(QtStoreProbe LANGUAGES CXX)

find_package(Qt6 6.9.3 EXACT REQUIRED COMPONENTS
    Core Gui GuiPrivate Concurrent Widgets Svg Qml Quick QuickControls2)

if(NOT APPLE OR NOT CMAKE_SYSTEM_NAME STREQUAL "Darwin")
    message(FATAL_ERROR "The Store Qt SDK probe requires macOS")
endif()

# The public SDK probe reads only the selected imported QtCore target. No app
# archive, app build scripts or application options are loaded here.
get_target_property(core_includes Qt6::Core INTERFACE_INCLUDE_DIRECTORIES)
set(config_headers "")
foreach(directory IN LISTS core_includes)
    if(directory MATCHES "\\$<")
        message(FATAL_ERROR "Cannot resolve QtCore's exported include directory")
    endif()
    foreach(suffix qconfig.h QtCore/qconfig.h Headers/qconfig.h)
        if(EXISTS "${directory}/${suffix}" AND NOT IS_DIRECTORY "${directory}/${suffix}")
            get_filename_component(config "${directory}/${suffix}" REALPATH)
            list(APPEND config_headers "${config}")
        endif()
    endforeach()
endforeach()
list(REMOVE_DUPLICATES config_headers)
list(LENGTH config_headers config_count)
if(NOT config_count EQUAL 1)
    message(FATAL_ERROR "Expected one qconfig.h exported by the selected QtCore target")
endif()
list(GET config_headers 0 config)
file(STRINGS "${config}" store_flags
    REGEX "^[ \t]*#[ \t]*(define|undef)[ \t]+QT_FEATURE_appstore_compliant([ \t]|$)")
list(LENGTH store_flags store_flag_count)
if(NOT store_flag_count EQUAL 1 OR NOT store_flags MATCHES "^[ \t]*#[ \t]*define[ \t]+QT_FEATURE_appstore_compliant[ \t]+1[ \t]*$")
    message(FATAL_ERROR "The selected QtCore must define QT_FEATURE_appstore_compliant=1")
endif()
file(SHA256 "${config}" config_sha256)
string(REPLACE "\\" "\\\\" config_json "${config}")
string(REPLACE "\"" "\\\"" config_json "${config_json}")
string(REPLACE "\n" "\\n" config_json "${config_json}")
string(REPLACE "\r" "\\r" config_json "${config_json}")
string(REPLACE "\t" "\\t" config_json "${config_json}")
file(WRITE "${CMAKE_BINARY_DIR}/gameremote-mac-app-store-qt.json"
    "{\n  \"scope\": \"Qt SDK configure-time feature check; no application source loaded\",\n  \"qt_version\": \"${Qt6Core_VERSION}\",\n  \"qconfig_header\": \"${config_json}\",\n  \"qconfig_sha256\": \"${config_sha256}\",\n  \"appstore_compliant\": 1\n}\n")

add_executable(qt_store_probe main.cpp)
target_compile_features(qt_store_probe PRIVATE cxx_std_17)
target_link_libraries(qt_store_probe PRIVATE
    Qt6::Core Qt6::Gui Qt6::GuiPrivate Qt6::Concurrent Qt6::Widgets
    Qt6::Svg Qt6::Qml Qt6::Quick Qt6::QuickControls2)
