# Public metadata only. Store archives must supply every field explicitly.
option(CHIAKI_IOS_STORE_RELEASE "Require publisher metadata for a signed store archive" OFF)
if(CHIAKI_IOS_STORE_RELEASE)
  set(_gr_bundle_default "")
  set(_gr_version_default "")
  set(_gr_build_default "")
else()
  set(_gr_bundle_default "org.example.RemotePlayPrototype.iOS")
  set(_gr_version_default "1.10.0")
  set(_gr_build_default "2")
endif()
set(CHIAKI_IOS_BUNDLE_IDENTIFIER "${_gr_bundle_default}" CACHE STRING "Publisher-owned iOS bundle identifier")
set(CHIAKI_IOS_DEVELOPMENT_TEAM "" CACHE STRING "Apple development team identifier")
set(CHIAKI_IOS_VERSION "${_gr_version_default}" CACHE STRING "Marketing version: major.minor.patch")
set(CHIAKI_IOS_BUILD_NUMBER "${_gr_build_default}" CACHE STRING "App Store build number")
set(CHIAKI_IOS_PRIVACY_URL "" CACHE STRING "Public HTTPS privacy policy URL")
set(CHIAKI_IOS_SUPPORT_URL "" CACHE STRING "Public HTTPS support URL")
set(CHIAKI_IOS_SOURCE_URL "" CACHE STRING "Public HTTPS corresponding-source URL for this exact build")
set(CHIAKI_IOS_EXPORT_CLASSIFICATION "" CACHE STRING "Export declaration: exempt, non-exempt, or defer-to-app-store-connect")
set_property(CACHE CHIAKI_IOS_EXPORT_CLASSIFICATION PROPERTY STRINGS "" exempt non-exempt defer-to-app-store-connect)

if(PYTHON_EXECUTABLE)
  set(_gr_metadata_python "${PYTHON_EXECUTABLE}")
else()
  find_program(_gr_metadata_python NAMES python3 REQUIRED)
endif()
set(_gr_validation_args)
if(CHIAKI_IOS_STORE_RELEASE)
  list(APPEND _gr_validation_args --store)
endif()
foreach(field BUNDLE_IDENTIFIER DEVELOPMENT_TEAM VERSION BUILD_NUMBER PRIVACY_URL SUPPORT_URL SOURCE_URL EXPORT_CLASSIFICATION)
  # CMake lists split semicolons before execute_process. Reject that separator
  # before constructing argv, so metadata cannot add validator options.
  # URL semicolons must be percent-encoded, as required by the Python validator.
  string(FIND "${CHIAKI_IOS_${field}}" ";" _gr_list_separator)
  if(NOT _gr_list_separator EQUAL -1)
    message(FATAL_ERROR "${field} must not contain a semicolon")
  endif()
  string(TOLOWER "${field}" argument)
  string(REPLACE "_" "-" argument "${argument}")
  # Keep each value as one process argument, including empty strings.
  list(APPEND _gr_validation_args "--${argument}=${CHIAKI_IOS_${field}}")
endforeach()
execute_process(
  COMMAND "${_gr_metadata_python}" -I "${CMAKE_CURRENT_LIST_DIR}/../scripts/release_config.py" ${_gr_validation_args}
  RESULT_VARIABLE _gr_validation_result OUTPUT_VARIABLE _gr_validation_output ERROR_VARIABLE _gr_validation_error)
if(NOT _gr_validation_result EQUAL 0)
  message(FATAL_ERROR "${_gr_validation_error}")
endif()
message(STATUS "${_gr_validation_output}")

foreach(field PRIVACY_URL SUPPORT_URL SOURCE_URL)
  string(REPLACE "&" "&amp;" CHIAKI_IOS_${field}_XML "${CHIAKI_IOS_${field}}")
  # MACOSX_BUNDLE_INFO_PLIST undergoes another configure pass in CMake.
  # Keep URL @ characters as XML entities until the final plist is parsed.
  string(REPLACE "@" "&#64;" CHIAKI_IOS_${field}_XML "${CHIAKI_IOS_${field}_XML}")
endforeach()
# Explicit deferral leaves both encryption keys absent for Apple's upload questionnaire.
# An unspecified development build also omits the key; store input cannot be empty.
set(GR_IOS_EXPORT_PLIST_ENTRY "")
if(CHIAKI_IOS_EXPORT_CLASSIFICATION STREQUAL "exempt")
  set(GR_IOS_EXPORT_PLIST_ENTRY "<key>ITSAppUsesNonExemptEncryption</key><false/>")
elseif(CHIAKI_IOS_EXPORT_CLASSIFICATION STREQUAL "non-exempt")
  set(GR_IOS_EXPORT_PLIST_ENTRY "<key>ITSAppUsesNonExemptEncryption</key><true/>")
endif()
set(GR_IOS_INFO_PLIST "${CMAKE_CURRENT_BINARY_DIR}/GameRemote-Info.plist")
configure_file("${CMAKE_CURRENT_LIST_DIR}/../App/Info.plist.in" "${GR_IOS_INFO_PLIST}" @ONLY)
