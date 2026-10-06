include_guard(GLOBAL)
include(FetchContent)

# Keep Oboe and the NDK static libc++ in the single JNI shared library. An AAR
# prefab contains already-linked .so files that do not inherit our linker flags.
# Source: https://github.com/google/oboe/tree/1.10.0 (Apache-2.0).
# Runtime constraint: https://developer.android.com/ndk/guides/cpp-support#static_runtimes
function(chiaki_add_static_oboe)
    if(NOT ANDROID OR NOT ANDROID_STL STREQUAL "c++_static")
        message(FATAL_ERROR "Oboe source build requires Android with c++_static")
    endif()
    set(BUILD_SHARED_LIBS OFF)
    set(oboe_archive_url "https://codeload.github.com/google/oboe/tar.gz/refs/tags/1.10.0")
    set(oboe_archive_sha256 "0e4245f8860c4287040a5d76501c588490bcc9cb57614c486c0c201a5dde3e9f")
    FetchContent_Declare(chiaki_oboe
        URL "${oboe_archive_url}"
        URL_HASH "SHA256=${oboe_archive_sha256}"
    )
    FetchContent_MakeAvailable(chiaki_oboe)
    get_target_property(oboe_library_type oboe TYPE)
    if(NOT oboe_library_type STREQUAL "STATIC_LIBRARY")
        message(FATAL_ERROR "Oboe must be static: multiple shared C++ runtimes are unsafe")
    endif()
    # Upstream's raw -std=c++17 flag can be overridden by an inherited CMake
    # standard flag. Express the requirement in CMake and pass it to JNI users.
    target_compile_features(oboe PUBLIC cxx_std_17)
    set_target_properties(oboe PROPERTIES
        POSITION_INDEPENDENT_CODE ON
        CXX_STANDARD 17
        CXX_STANDARD_REQUIRED ON
    )

    # Preserve upstream licence and corresponding-source provenance for release
    # assembly. FetchContent sources remain under the build tree's _deps/.
    set(notice_dir "${CMAKE_BINARY_DIR}/release-notices")
    file(MAKE_DIRECTORY "${notice_dir}")
    configure_file("${chiaki_oboe_SOURCE_DIR}/LICENSE"
        "${notice_dir}/oboe-1.10.0-LICENSE.txt" COPYONLY)
    file(WRITE "${notice_dir}/oboe-1.10.0-SOURCE.txt"
        "Oboe 1.10.0\nLicence: Apache-2.0\nSource: ${oboe_archive_url}\nSHA256: ${oboe_archive_sha256}\nBuild: STATIC with position-independent code, linked into chiaki-jni.\n")
endfunction()

chiaki_add_static_oboe()
