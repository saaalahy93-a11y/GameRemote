# Keep the legacy settings namespace so existing console registrations survive
# the rebrand. Distribution builds must supply a publisher-owned bundle ID.
set(CHIAKI_SETTINGS_ORGANIZATION "Chiaki" CACHE STRING "Desktop settings organization")
set(CHIAKI_SETTINGS_APPLICATION "Chiaki" CACHE STRING "Desktop settings application")
set(CHIAKI_BUNDLE_IDENTIFIER "org.example.GameRemote" CACHE STRING "macOS application bundle identifier")

foreach(identity CHIAKI_SETTINGS_ORGANIZATION CHIAKI_SETTINGS_APPLICATION CHIAKI_BUNDLE_IDENTIFIER)
	if(NOT "${${identity}}" MATCHES "^[A-Za-z0-9][A-Za-z0-9_.-]*$")
		message(FATAL_ERROR "${identity} must contain only letters, numbers, dots, underscores or hyphens")
	endif()
endforeach()
if(NOT CHIAKI_BUNDLE_IDENTIFIER MATCHES "^[A-Za-z0-9-]+(\\.[A-Za-z0-9-]+)+$")
	message(FATAL_ERROR "CHIAKI_BUNDLE_IDENTIFIER must be a reverse-DNS identifier")
endif()
