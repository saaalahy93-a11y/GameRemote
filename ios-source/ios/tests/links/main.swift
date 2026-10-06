import Foundation

func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() { fatalError(message) }
}

let empty = AppLinks(info: [:])
check(empty.privacyPolicy == nil && empty.support == nil && empty.source == nil, "Development builds do not fabricate public links")
// Fixture only: these known HTTPS endpoints do not supply publisher defaults.
let privacy = "https://www.apple.com/legal/privacy/?lang=en&view=full"
let support = "https://support.apple.com/"
let source = "https://github.com/"
let configured = AppLinks(info: ["GameRemotePrivacyPolicyURL": privacy, "GameRemoteSupportURL": support, "GameRemoteSourceURL": source])
check(configured.privacyPolicy?.absoluteString == privacy, "Configured privacy URL, including query parameters, is preserved")
check(configured.support?.absoluteString == support && configured.source?.absoluteString == source, "Support and corresponding-source keys reach the app")
check(AppLinks(info: ["GameRemotePrivacyPolicyURL": "HTTPS://www.apple.com/privacy"]).privacyPolicy != nil, "HTTPS scheme is case insensitive, matching release validation")
for invalid: Any in ["", " ", "http://www.apple.com/privacy", "javascript:alert(1)", "file:///tmp/policy", "https:///privacy", "https://user:password@www.apple.com/", "https://www.apple.com/a b", "https://www.apple.com/\n", 42] {
    let links = AppLinks(info: ["GameRemotePrivacyPolicyURL": invalid, "GameRemoteSupportURL": invalid, "GameRemoteSourceURL": invalid])
    check(links.privacyPolicy == nil && links.support == nil && links.source == nil, "Unsafe or missing links are unavailable")
}
print("Public-link configuration, development absence and URL rejection tests passed")
