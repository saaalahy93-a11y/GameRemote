
include(FetchContent)

set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
set(BUILD_TESTING OFF CACHE BOOL "" FORCE)
set(BUILD_APPS OFF CACHE BOOL "" FORCE)
set(DISABLE_EXTRA_LIBS ON CACHE BOOL "" FORCE)
set(DISABLE_BSON_OUTPUT ON CACHE BOOL "" FORCE)

set(GAMEREMOTE_JSONC_SOURCE_URL "https://github.com/json-c/json-c/archive/refs/tags/json-c-0.17-20230812.tar.gz")
set(GAMEREMOTE_JSONC_SOURCE_SHA256 "024d302a3aadcbf9f78735320a6d5aedf8b77876c8ac8bbb95081ca55054c7eb")
FetchContent_Declare(json-c
	URL "${GAMEREMOTE_JSONC_SOURCE_URL}"
	URL_HASH "SHA256=${GAMEREMOTE_JSONC_SOURCE_SHA256}"
)
FetchContent_MakeAvailable(json-c)

# Preserve the exact fetched licence and source identity for release assembly.
file(MAKE_DIRECTORY "${CMAKE_BINARY_DIR}/release-notices")
configure_file("${json-c_SOURCE_DIR}/COPYING"
	"${CMAKE_BINARY_DIR}/release-notices/json-c-0.17-LICENSE.txt" COPYONLY)
file(WRITE "${CMAKE_BINARY_DIR}/release-notices/json-c-0.17-SOURCE.txt"
	"Declared upstream source: ${GAMEREMOTE_JSONC_SOURCE_URL}\n"
	"Expected archive SHA256: ${GAMEREMOTE_JSONC_SOURCE_SHA256}\n")

# GameRemote includes headers as <json-c/json_object.h> but FetchContent provides
# them without the json-c/ prefix. Create a symlink bridge directory.
set(JSONC_PREFIX_INCLUDE_DIR "${CMAKE_BINARY_DIR}/_deps/json-c-prefix-include")
file(MAKE_DIRECTORY "${JSONC_PREFIX_INCLUDE_DIR}")
if(NOT EXISTS "${JSONC_PREFIX_INCLUDE_DIR}/json-c")
	file(CREATE_LINK "${json-c_SOURCE_DIR}" "${JSONC_PREFIX_INCLUDE_DIR}/json-c" SYMBOLIC)
endif()
