
include(FetchContent)

set(UPNPC_BUILD_STATIC ON CACHE BOOL "" FORCE)
set(UPNPC_BUILD_SHARED OFF CACHE BOOL "" FORCE)
set(UPNPC_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(UPNPC_BUILD_SAMPLE OFF CACHE BOOL "" FORCE)
set(UPNPC_NO_INSTALL ON CACHE BOOL "" FORCE)

set(GAMEREMOTE_MINIUPNPC_SOURCE_URL "https://github.com/miniupnp/miniupnp/archive/refs/tags/miniupnpc_2_2_8.tar.gz")
set(GAMEREMOTE_MINIUPNPC_SOURCE_SHA256 "3d0d49f761f09c1321ceb663d1b008825361d7bd242640c60ae467e82642502a")
FetchContent_Declare(miniupnpc
	URL "${GAMEREMOTE_MINIUPNPC_SOURCE_URL}"
	URL_HASH "SHA256=${GAMEREMOTE_MINIUPNPC_SOURCE_SHA256}"
	SOURCE_SUBDIR miniupnpc
)
FetchContent_MakeAvailable(miniupnpc)

# Preserve the exact fetched licence and source identity for release assembly.
file(MAKE_DIRECTORY "${CMAKE_BINARY_DIR}/release-notices")
configure_file("${miniupnpc_SOURCE_DIR}/miniupnpc/LICENSE"
	"${CMAKE_BINARY_DIR}/release-notices/miniupnpc-2.2.8-LICENSE.txt" COPYONLY)
file(WRITE "${CMAKE_BINARY_DIR}/release-notices/miniupnpc-2.2.8-SOURCE.txt"
	"Declared upstream source: ${GAMEREMOTE_MINIUPNPC_SOURCE_URL}\n"
	"Expected archive SHA256: ${GAMEREMOTE_MINIUPNPC_SOURCE_SHA256}\n")

# GameRemote includes headers as <miniupnpc/miniupnpc.h> but FetchContent provides
# them without the prefix. Create a symlink bridge directory.
set(MINIUPNPC_PREFIX_INCLUDE_DIR "${CMAKE_BINARY_DIR}/_deps/miniupnpc-prefix-include")
file(MAKE_DIRECTORY "${MINIUPNPC_PREFIX_INCLUDE_DIR}")
if(NOT EXISTS "${MINIUPNPC_PREFIX_INCLUDE_DIR}/miniupnpc")
	file(CREATE_LINK "${miniupnpc_SOURCE_DIR}/miniupnpc/include" "${MINIUPNPC_PREFIX_INCLUDE_DIR}/miniupnpc" SYMBOLIC)
endif()
