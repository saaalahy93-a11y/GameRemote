# nanopb's CMake static library cannot carry resources. Preserve its upstream
# privacy manifest in a separate resource bundle, as its Swift package does.
function(gameremote_add_nanopb_privacy target)
  set(manifest "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/../../third-party/nanopb/spm_resources/PrivacyInfo.xcprivacy")
  set(bundle "${CMAKE_CURRENT_BINARY_DIR}/nanopb_Privacy.bundle")
  configure_file("${manifest}" "${bundle}/PrivacyInfo.xcprivacy" COPYONLY)
  file(WRITE "${bundle}/Info.plist" [=[<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleIdentifier</key><string>org.nanopb.nanopb-Privacy</string>
  <key>CFBundleName</key><string>nanopb_Privacy</string>
  <key>CFBundlePackageType</key><string>BNDL</string>
  <key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
  <key>CFBundleVersion</key><string>1</string>
</dict></plist>
]=])
  set(resources "${bundle}/PrivacyInfo.xcprivacy" "${bundle}/Info.plist")
  set_source_files_properties(${resources} PROPERTIES MACOSX_PACKAGE_LOCATION "Resources/nanopb_Privacy.bundle")
  target_sources(${target} PRIVATE ${resources})
endfunction()
