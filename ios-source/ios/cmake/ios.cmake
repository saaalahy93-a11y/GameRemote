set(CMAKE_SYSTEM_NAME iOS)
set(IOS TRUE)
set(CMAKE_OSX_DEPLOYMENT_TARGET "16.0" CACHE STRING "Minimum supported iOS")
set(CMAKE_OSX_SYSROOT "iphoneos" CACHE STRING "iphoneos or iphonesimulator")
set(CMAKE_OSX_ARCHITECTURES "arm64" CACHE STRING "Target architecture(s)")
# Feature probes must link, otherwise unavailable functions look present.
set(CMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED "NO" CACHE STRING "Disable signing for unsigned build and feature probes")
