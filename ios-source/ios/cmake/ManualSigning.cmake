# Called only for the app target after normal properties are configured. Compiler
# probes and every dependency retain CMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED=NO.
option(CHIAKI_IOS_MANUAL_SIGNING "Explicit manual signing for the GameRemote app target" OFF)

function(gameremote_configure_manual_signing target)
    if(NOT CHIAKI_IOS_MANUAL_SIGNING)
        return()
    endif()
    if(NOT "${target}" STREQUAL "GameRemoteIOS")
        message(FATAL_ERROR "Manual signing is restricted to the GameRemoteIOS app target")
    endif()
    foreach(field IDENTITY PROFILE_UUID KEYCHAIN_FLAGS)
        if("${CHIAKI_IOS_SIGNING_${field}}" STREQUAL "")
            message(FATAL_ERROR "Explicit CHIAKI_IOS_SIGNING_${field} is required")
        endif()
    endforeach()
    set_target_properties(${target} PROPERTIES
        # A cached manual configuration still defaults to unsigned. Only the
        # archive command explicitly sets this app-only variable to YES.
        XCODE_ATTRIBUTE_GR_IOS_ARCHIVE_SIGNING "NO"
        XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED "$(GR_IOS_ARCHIVE_SIGNING)"
        XCODE_ATTRIBUTE_CODE_SIGNING_REQUIRED "$(GR_IOS_ARCHIVE_SIGNING)"
        XCODE_ATTRIBUTE_CODE_SIGN_STYLE "Manual"
        XCODE_ATTRIBUTE_CODE_SIGN_IDENTITY "${CHIAKI_IOS_SIGNING_IDENTITY}"
        XCODE_ATTRIBUTE_PROVISIONING_PROFILE_SPECIFIER "${CHIAKI_IOS_SIGNING_PROFILE_UUID}"
        XCODE_ATTRIBUTE_OTHER_CODE_SIGN_FLAGS "${CHIAKI_IOS_SIGNING_KEYCHAIN_FLAGS}"
    )
endfunction()
