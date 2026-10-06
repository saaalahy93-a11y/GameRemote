cmake_minimum_required(VERSION 3.28)
project(GameRemoteIOS LANGUAGES C CXX Swift)
if(NOT CMAKE_SYSTEM_NAME STREQUAL "iOS")
  message(FATAL_ERROR "Use -DCMAKE_TOOLCHAIN_FILE=ios/cmake/ios.cmake with full Xcode and an iOS SDK")
endif()
include("${CMAKE_CURRENT_SOURCE_DIR}/cmake/ReleaseConfig.cmake")
# Only the app belongs in an .xcarchive; static dependencies remain build inputs.
set(CMAKE_XCODE_ATTRIBUTE_SKIP_INSTALL YES)
set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
set(BUILD_TESTING OFF CACHE BOOL "" FORCE)
include(FetchContent)
# Source IDs are immutable upstream commits. Repository submodules remain pinned by gitlinks.
FetchContent_Declare(ios_opus GIT_REPOSITORY https://github.com/xiph/opus.git GIT_TAG ddbe48383984d56acd9e1ab6a090c54ca6b735a6)
FetchContent_Declare(ios_event GIT_REPOSITORY https://github.com/libevent/libevent.git GIT_TAG 5df3037d10556bfcb675bc73e516978b75fc7bc7)
FetchContent_Declare(ios_json GIT_REPOSITORY https://github.com/json-c/json-c.git GIT_TAG b4c371fa0cbc4dcbaccc359ce9e957a22988fb34)
FetchContent_Declare(ios_upnp GIT_REPOSITORY https://github.com/miniupnp/miniupnp.git GIT_TAG b55145ec095652289a59c33603f3abafee898273)
set(OPUS_BUILD_TESTING OFF CACHE BOOL "" FORCE)
set(OPUS_BUILD_PROGRAMS OFF CACHE BOOL "" FORCE)
set(OPUS_INSTALL_PKG_CONFIG_MODULE OFF CACHE BOOL "" FORCE)
set(EVENT__LIBRARY_TYPE STATIC CACHE STRING "" FORCE)
set(EVENT__DISABLE_OPENSSL ON CACHE BOOL "" FORCE)
set(EVENT__DISABLE_TESTS ON CACHE BOOL "" FORCE)
set(EVENT__DISABLE_REGRESS ON CACHE BOOL "" FORCE)
set(EVENT__DISABLE_SAMPLES ON CACHE BOOL "" FORCE)
set(EVENT__DISABLE_BENCHMARK ON CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(ios_opus ios_event)
# Populate only; core's existing modules configure the json-c and miniupnpc targets.
FetchContent_GetProperties(ios_json)
if(NOT ios_json_POPULATED)
  FetchContent_Populate(ios_json)
endif()
FetchContent_GetProperties(ios_upnp)
if(NOT ios_upnp_POPULATED)
  FetchContent_Populate(ios_upnp)
endif()
set(FETCHCONTENT_SOURCE_DIR_JSON-C "${ios_json_SOURCE_DIR}" CACHE PATH "" FORCE)
set(FETCHCONTENT_SOURCE_DIR_MINIUPNPC "${ios_upnp_SOURCE_DIR}" CACHE PATH "" FORCE)
list(PREPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_SOURCE_DIR}/cmake")
# Prevent host Homebrew pkg-config libraries contaminating the iOS link.
set(PKG_CONFIG_EXECUTABLE "" CACHE FILEPATH "" FORCE)
set(CMAKE_DISABLE_FIND_PACKAGE_PkgConfig TRUE)
foreach(feature TESTS CLI GUI ANDROID BOREALIS SETSU STEAMDECK_NATIVE SPEEX RUDP FFMPEG_DECODER PI_DECODER STEAM_SHORTCUT)
  set(CHIAKI_ENABLE_${feature} OFF CACHE STRING "" FORCE)
endforeach()
set(CHIAKI_LIB_ENABLE_OPUS ON CACHE BOOL "" FORCE)
set(CHIAKI_LIB_ENABLE_MBEDTLS ON CACHE BOOL "" FORCE)
set(CHIAKI_LIB_MBEDTLS_EXTERNAL_PROJECT ON CACHE BOOL "" FORCE)
# Keep upstream warnings visible without making new Xcode diagnostics fatal.
set(MBEDTLS_FATAL_WARNINGS OFF CACHE BOOL "" FORCE)
set(CHIAKI_LIB_JSONC_EXTERNAL_PROJECT ON CACHE BOOL "" FORCE)
set(CHIAKI_LIB_MINIUPNPC_EXTERNAL_PROJECT ON CACHE BOOL "" FORCE)
set(CHIAKI_USE_SYSTEM_CURL OFF CACHE STRING "" FORCE)
set(CHIAKI_USE_SYSTEM_JERASURE OFF CACHE STRING "" FORCE)
set(CHIAKI_USE_SYSTEM_NANOPB OFF CACHE STRING "" FORCE)
# curl submodule: WebSockets remains enabled by core; native TLS avoids host OpenSSL.
set(CURL_USE_SECTRANSP ON CACHE BOOL "" FORCE)
set(CURL_USE_OPENSSL OFF CACHE BOOL "" FORCE)
set(CURL_USE_LIBPSL OFF CACHE BOOL "" FORCE)
set(CURL_USE_LIBSSH2 OFF CACHE BOOL "" FORCE)
set(CURL_USE_LIBSSH OFF CACHE BOOL "" FORCE)
set(CURL_ZLIB OFF CACHE BOOL "" FORCE)
set(CURL_BROTLI OFF CACHE BOOL "" FORCE)
set(CURL_ZSTD OFF CACHE BOOL "" FORCE)
set(USE_LIBIDN2 OFF CACHE BOOL "" FORCE)
# pkg-config discovery is disabled above, so curl must not call it; HTTP/2 is unused on this LAN path.
set(CURL_USE_PKGCONFIG OFF CACHE BOOL "" FORCE)
set(USE_NGHTTP2 OFF CACHE BOOL "" FORCE)
set(ENABLE_THREADED_RESOLVER ON CACHE BOOL "" FORCE)
add_subdirectory("${CMAKE_CURRENT_SOURCE_DIR}/.." core EXCLUDE_FROM_ALL)
add_library(GameRemoteBridge STATIC Bridge/GameRemoteBridge.c)
target_compile_features(GameRemoteBridge PRIVATE c_std_11)
target_include_directories(GameRemoteBridge PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/Bridge")
target_link_libraries(GameRemoteBridge PUBLIC chiaki-lib PRIVATE mbedtls mbedx509 mbedcrypto)
# The core defines this in its directory; clients must use the same struct layout.
target_compile_definitions(GameRemoteBridge PRIVATE CHIAKI_LIB_ENABLE_MBEDTLS)

# Exact licence texts of the statically linked sources, assembled from the trees this build compiles.
FetchContent_GetProperties(mbedtls SOURCE_DIR ios_mbedtls_SOURCE_DIR)
set(GR_THIRD_PARTY "${CMAKE_CURRENT_SOURCE_DIR}/../third-party")
set(GR_NOTICE_SOURCES
  "Opus|${ios_opus_SOURCE_DIR}/COPYING"
  "libevent|${ios_event_SOURCE_DIR}/LICENSE"
  "json-c|${ios_json_SOURCE_DIR}/COPYING"
  "MiniUPnPc|${ios_upnp_SOURCE_DIR}/miniupnpc/LICENSE"
  "Mbed TLS|${ios_mbedtls_SOURCE_DIR}/LICENSE"
  "curl|${GR_THIRD_PARTY}/curl/COPYING"
  "nanopb|${GR_THIRD_PARTY}/nanopb/LICENSE.txt"
  "GF-Complete|${GR_THIRD_PARTY}/gf-complete/COPYING"
  "Jerasure|${GR_THIRD_PARTY}/jerasure/COPYING")
set(GR_NOTICES "${CMAKE_CURRENT_BINARY_DIR}/ThirdPartyNotices.txt")
set(GR_NOTICE_TEXT "Third-party components statically linked into GameRemote for iPhone and iPad.")
foreach(entry IN LISTS GR_NOTICE_SOURCES)
  string(FIND "${entry}" "|" split)
  string(SUBSTRING "${entry}" 0 ${split} component)
  math(EXPR split "${split} + 1")
  string(SUBSTRING "${entry}" ${split} -1 notice)
  if(NOT EXISTS "${notice}")
    message(FATAL_ERROR "Missing licence notice for ${component}: ${notice}")
  endif()
  file(READ "${notice}" text)
  string(APPEND GR_NOTICE_TEXT "\n\n==== ${component} ====\n\n${text}")
endforeach()
file(WRITE "${GR_NOTICES}" "${GR_NOTICE_TEXT}\n")

set(GR_APP_SOURCES
  App/GameRemoteApp.swift App/SessionModel.swift App/SessionPhase.swift App/ConsoleIndex.swift App/InputAggregator.swift
  App/Keychain.swift App/Media.swift App/MediaState.swift App/H264.swift App/Platform.swift App/Theme.swift App/ConsoleArtwork.swift
  App/HomeView.swift App/RegistrationViews.swift App/SupportViews.swift App/AppLinks.swift App/StreamView.swift App/TouchControls.swift App/TouchControlLayout.swift)
set(GR_APP_RESOURCES App/PrivacyInfo.xcprivacy App/Assets.xcassets "${CMAKE_CURRENT_SOURCE_DIR}/../LICENSES/AGPL-3.0-only-OpenSSL.txt" "${GR_NOTICES}")
add_executable(GameRemoteIOS MACOSX_BUNDLE ${GR_APP_SOURCES} ${GR_APP_RESOURCES})
set_source_files_properties(${GR_APP_RESOURCES} PROPERTIES MACOSX_PACKAGE_LOCATION Resources)
include("${CMAKE_CURRENT_SOURCE_DIR}/cmake/NanopbPrivacy.cmake")
gameremote_add_nanopb_privacy(GameRemoteIOS)
include("${CMAKE_CURRENT_SOURCE_DIR}/cmake/CurlPrivacy.cmake")
gameremote_add_curl_privacy(GameRemoteIOS)
target_compile_options(GameRemoteIOS PRIVATE "$<$<COMPILE_LANGUAGE:Swift>:-I${CMAKE_CURRENT_SOURCE_DIR}/Bridge>")
target_link_libraries(GameRemoteIOS PRIVATE GameRemoteBridge "-framework SwiftUI" "-framework UIKit" "-framework AVFoundation" "-framework VideoToolbox" "-framework GameController" "-framework Security" "-framework CoreMedia" "-framework AudioToolbox")
set_target_properties(GameRemoteIOS PROPERTIES
  OUTPUT_NAME GameRemote
  MACOSX_BUNDLE_INFO_PLIST "${GR_IOS_INFO_PLIST}"
  XCODE_GENERATE_SCHEME TRUE
  XCODE_ATTRIBUTE_PRODUCT_BUNDLE_IDENTIFIER "${CHIAKI_IOS_BUNDLE_IDENTIFIER}"
  XCODE_ATTRIBUTE_DEVELOPMENT_TEAM "${CHIAKI_IOS_DEVELOPMENT_TEAM}"
  XCODE_ATTRIBUTE_MARKETING_VERSION "${CHIAKI_IOS_VERSION}"
  XCODE_ATTRIBUTE_CURRENT_PROJECT_VERSION "${CHIAKI_IOS_BUILD_NUMBER}"
  XCODE_ATTRIBUTE_SKIP_INSTALL NO
  XCODE_ATTRIBUTE_INSTALL_PATH "$(LOCAL_APPS_DIR)"
  XCODE_ATTRIBUTE_TARGETED_DEVICE_FAMILY "1,2"
  XCODE_ATTRIBUTE_SWIFT_VERSION "5.0"
  XCODE_ATTRIBUTE_CODE_SIGN_STYLE "Automatic"
  XCODE_ATTRIBUTE_ASSETCATALOG_COMPILER_APPICON_NAME "AppIcon"
  XCODE_ATTRIBUTE_SWIFT_INCLUDE_PATHS "${CMAKE_CURRENT_SOURCE_DIR}/Bridge")
include("${CMAKE_CURRENT_SOURCE_DIR}/cmake/ManualSigning.cmake")
gameremote_configure_manual_signing(GameRemoteIOS)
