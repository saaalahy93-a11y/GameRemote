import Foundation

/// Public links supplied by the publisher at build time. Development builds may leave them unset.
struct AppLinks {
    static let current = AppLinks(info: Bundle.main.infoDictionary ?? [:])

    let privacyPolicy: URL?
    let support: URL?
    let source: URL?

    init(info: [String: Any]) {
        privacyPolicy = Self.httpsURL(info["GameRemotePrivacyPolicyURL"])
        support = Self.httpsURL(info["GameRemoteSupportURL"])
        source = Self.httpsURL(info["GameRemoteSourceURL"])
    }

    private static func httpsURL(_ value: Any?) -> URL? {
        guard let text = value as? String, !text.isEmpty,
              text.rangeOfCharacter(from: .whitespacesAndNewlines.union(.controlCharacters)) == nil,
              let components = URLComponents(string: text), components.scheme?.lowercased() == "https",
              let host = components.host, !host.isEmpty,
              components.user == nil, components.password == nil else { return nil }
        return components.url
    }
}
