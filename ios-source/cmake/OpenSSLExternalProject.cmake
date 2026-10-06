
include(ExternalProject)

# OpenSSL 3.5 is LTS through 2030-04-08. Pin the upstream release archive, not
# GitHub's generated source snapshot. Digest: the official release's .sha256 asset.
set(CHIAKI_OPENSSL_VERSION "3.5.9")
set(OPENSSL_INSTALL_DIR "${CMAKE_CURRENT_BINARY_DIR}/openssl-${CHIAKI_OPENSSL_VERSION}-install-prefix")
# OpenSSL upgrades can leave obsolete generated headers in an existing binary
# tree. Isolate source, binary, stamps and installed libraries per release.
set(CHIAKI_OPENSSL_PROJECT_PREFIX "${CMAKE_CURRENT_BINARY_DIR}/openssl-${CHIAKI_OPENSSL_VERSION}-prefix")
set(CHIAKI_OPENSSL_SOURCE_URL "https://github.com/openssl/openssl/releases/download/openssl-${CHIAKI_OPENSSL_VERSION}/openssl-${CHIAKI_OPENSSL_VERSION}.tar.gz")
set(CHIAKI_OPENSSL_SOURCE_SHA256 "603f5602e2eef00d77fbd429d34dcd5822bb301757a1bc9cdb24c670f1eb859a")

unset(OPENSSL_OS_COMPILER)
unset(OPENSSL_CONFIG_EXTRA_ARGS)
unset(OPENSSL_BUILD_ENV)

if(ANDROID_ABI)
	if(ANDROID_ABI STREQUAL "armeabi-v7a")
		set(OPENSSL_OS_COMPILER "android-arm")
	elseif(ANDROID_ABI STREQUAL "arm64-v8a")
		set(OPENSSL_OS_COMPILER "android-arm64")
	elseif(ANDROID_ABI STREQUAL "x86")
		set(OPENSSL_OS_COMPILER "android-x86")
	elseif(ANDROID_ABI STREQUAL "x86_64")
		set(OPENSSL_OS_COMPILER "android-x86_64")
	endif()

	set(OPENSSL_CONFIG_EXTRA_ARGS "-D__ANDROID_API__=${ANDROID_NATIVE_API_LEVEL}")
	get_filename_component(ANDROID_NDK_BIN_PATH "${CMAKE_C_COMPILER}" DIRECTORY)
	set(OPENSSL_BUILD_ENV "ANDROID_NDK_ROOT=${ANDROID_NDK}" "PATH=${ANDROID_NDK_BIN_PATH}:$ENV{PATH}")
else()
	if(UNIX AND NOT APPLE AND CMAKE_SIZEOF_VOID_P STREQUAL "8")
		set(OPENSSL_OS_COMPILER "linux-x86_64")
	endif()
endif()

if(NOT OPENSSL_OS_COMPILER)
	message(FATAL_ERROR "Failed to match OPENSSL_OS_COMPILER")
endif()

find_program(MAKE_EXE NAMES gmake make)
set(CHIAKI_DEPENDENCY_BUILD_JOBS "2" CACHE STRING "Maximum parallel jobs for external dependency builds")
if(NOT CHIAKI_DEPENDENCY_BUILD_JOBS MATCHES "^[1-9][0-9]*$")
	message(FATAL_ERROR "CHIAKI_DEPENDENCY_BUILD_JOBS must be a positive integer")
endif()
ExternalProject_Add(OpenSSL-ExternalProject
		PREFIX "${CHIAKI_OPENSSL_PROJECT_PREFIX}"
		URL "${CHIAKI_OPENSSL_SOURCE_URL}"
		URL_HASH "SHA256=${CHIAKI_OPENSSL_SOURCE_SHA256}"
		INSTALL_DIR "${OPENSSL_INSTALL_DIR}"
		CONFIGURE_COMMAND ${CMAKE_COMMAND} -E env ${OPENSSL_BUILD_ENV}
			# Core still uses deprecated EC_KEY/ECDH APIs; keep their default support.
			# Built-in providers keep mobile crypto independent of external modules.
			"<SOURCE_DIR>/Configure" "--prefix=<INSTALL_DIR>" --libdir=lib
			no-shared no-module no-dso enable-pic ${OPENSSL_CONFIG_EXTRA_ARGS} "${OPENSSL_OS_COMPILER}"
		BUILD_COMMAND ${CMAKE_COMMAND} -E env ${OPENSSL_BUILD_ENV} "${MAKE_EXE}" "-j${CHIAKI_DEPENDENCY_BUILD_JOBS}" build_libs
		INSTALL_COMMAND ${CMAKE_COMMAND} -E env ${OPENSSL_BUILD_ENV} "${MAKE_EXE}" install_dev)

# Retain the exact licence from the checksum-verified source for release assembly.
set(CHIAKI_OPENSSL_NOTICE_DIR "${CMAKE_BINARY_DIR}/release-notices")
file(MAKE_DIRECTORY "${CHIAKI_OPENSSL_NOTICE_DIR}")
file(WRITE "${CHIAKI_OPENSSL_NOTICE_DIR}/openssl-${CHIAKI_OPENSSL_VERSION}-SOURCE.txt"
	"OpenSSL ${CHIAKI_OPENSSL_VERSION}\nLicence: Apache-2.0\nSource: ${CHIAKI_OPENSSL_SOURCE_URL}\nSHA256: ${CHIAKI_OPENSSL_SOURCE_SHA256}\nLTS support ends: 2030-04-08\nBuild: static PIC, libdir=lib, no dynamically loaded modules; deprecated APIs retained.\n")
ExternalProject_Add_Step(OpenSSL-ExternalProject release-notices
	COMMAND "${CMAKE_COMMAND}" -E copy_if_different
		"<SOURCE_DIR>/LICENSE.txt" "${CHIAKI_OPENSSL_NOTICE_DIR}/openssl-${CHIAKI_OPENSSL_VERSION}-LICENSE.txt"
	DEPENDEES download
	DEPENDERS configure)

add_library(OpenSSL_Crypto INTERFACE)
add_dependencies(OpenSSL_Crypto OpenSSL-ExternalProject)
if(${CMAKE_VERSION} VERSION_GREATER_EQUAL "3.13.0")
	target_link_directories(OpenSSL_Crypto INTERFACE "${OPENSSL_INSTALL_DIR}/lib")
else()
	link_directories("${OPENSSL_INSTALL_DIR}/lib")
endif()
target_link_libraries(OpenSSL_Crypto INTERFACE crypto ssl)
target_include_directories(OpenSSL_Crypto INTERFACE "${OPENSSL_INSTALL_DIR}/include")

# Create standard OpenSSL::* IMPORTED INTERFACE targets for find_package(OpenSSL) consumers
# (e.g. bundled curl). Using IMPORTED INTERFACE avoids file-existence checks that IMPORTED
# STATIC would require, and IMPORTED targets are excluded from curl's export sets.
file(MAKE_DIRECTORY "${OPENSSL_INSTALL_DIR}/include")

if(NOT TARGET OpenSSL::Crypto)
	add_library(OpenSSL::Crypto INTERFACE IMPORTED GLOBAL)
	set_property(TARGET OpenSSL::Crypto PROPERTY INTERFACE_INCLUDE_DIRECTORIES "${OPENSSL_INSTALL_DIR}/include")
	set_property(TARGET OpenSSL::Crypto PROPERTY INTERFACE_LINK_DIRECTORIES "${OPENSSL_INSTALL_DIR}/lib")
	set_property(TARGET OpenSSL::Crypto PROPERTY INTERFACE_LINK_LIBRARIES crypto)
	add_dependencies(OpenSSL::Crypto OpenSSL-ExternalProject)
endif()

if(NOT TARGET OpenSSL::SSL)
	add_library(OpenSSL::SSL INTERFACE IMPORTED GLOBAL)
	set_property(TARGET OpenSSL::SSL PROPERTY INTERFACE_INCLUDE_DIRECTORIES "${OPENSSL_INSTALL_DIR}/include")
	set_property(TARGET OpenSSL::SSL PROPERTY INTERFACE_LINK_DIRECTORIES "${OPENSSL_INSTALL_DIR}/lib")
	set_property(TARGET OpenSSL::SSL PROPERTY INTERFACE_LINK_LIBRARIES "ssl;OpenSSL::Crypto")
	add_dependencies(OpenSSL::SSL OpenSSL-ExternalProject)
endif()

# Mark OpenSSL as found so FindOpenSSL.cmake is a no-op
set(OPENSSL_FOUND TRUE CACHE BOOL "" FORCE)
set(OpenSSL_FOUND TRUE CACHE BOOL "" FORCE)
set(OPENSSL_VERSION "${CHIAKI_OPENSSL_VERSION}" CACHE STRING "" FORCE)
set(OPENSSL_INCLUDE_DIR "${OPENSSL_INSTALL_DIR}/include" CACHE PATH "" FORCE)
set(OPENSSL_CRYPTO_LIBRARY "${OPENSSL_INSTALL_DIR}/lib/libcrypto.a" CACHE FILEPATH "" FORCE)
set(OPENSSL_SSL_LIBRARY "${OPENSSL_INSTALL_DIR}/lib/libssl.a" CACHE FILEPATH "" FORCE)
