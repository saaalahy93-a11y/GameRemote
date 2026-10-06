# SecureTransport uses Security and CoreFoundation on iOS. The pinned curl
# CMake configuration also requests the macOS-only CoreServices framework.
# Adapt a build-local source copy; never modify the recorded submodule.
set(CHIAKI_CURL_SOURCE_DIR "${CMAKE_CURRENT_BINARY_DIR}/curl-ios-source")
file(COPY "${CMAKE_CURRENT_SOURCE_DIR}/curl/"
    DESTINATION "${CHIAKI_CURL_SOURCE_DIR}" PATTERN ".git" EXCLUDE)
file(READ "${CMAKE_CURRENT_SOURCE_DIR}/curl/CMakeLists.txt" _curl_contents)

set(_curl_services_lookup "  find_library(CORESERVICES_FRAMEWORK \"CoreServices\")\n  mark_as_advanced(CORESERVICES_FRAMEWORK)")
set(_curl_services_check "  if(NOT CORESERVICES_FRAMEWORK)\n    message(FATAL_ERROR \"CoreServices framework not found\")\n  endif()")
set(_curl_framework_links "  list(APPEND CURL_LIBS \"-framework CoreFoundation\" \"-framework CoreServices\")")
foreach(_fragment _curl_services_lookup _curl_services_check _curl_framework_links)
    string(FIND "${_curl_contents}" "${${_fragment}}" _position)
    if(_position EQUAL -1)
        message(FATAL_ERROR "Bundled curl does not match the iOS framework adaptation")
    endif()
endforeach()
string(REPLACE "${_curl_services_lookup}" "" _curl_contents "${_curl_contents}")
string(REPLACE "${_curl_services_check}" "" _curl_contents "${_curl_contents}")
string(REPLACE "${_curl_framework_links}" "  list(APPEND CURL_LIBS \"-framework CoreFoundation\")" _curl_contents "${_curl_contents}")
file(WRITE "${CHIAKI_CURL_SOURCE_DIR}/CMakeLists.txt" "${_curl_contents}")
