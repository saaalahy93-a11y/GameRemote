import Foundation
import Security
import GameRemoteBridge

protocol CredentialStore {
    func save(_ value: CBCredentials, host: String) throws
    func load(host: String) -> CBCredentials?
    func delete(host: String) throws
    func deleteAll() throws
}
struct KeychainCredentials: CredentialStore {
    func save(_ value: CBCredentials, host: String) throws { try LocalCredentials.save(value, host: host) }
    func load(host: String) -> CBCredentials? { LocalCredentials.load(host: host) }
    func delete(host: String) throws { try LocalCredentials.delete(host: host) }
    func deleteAll() throws { try LocalCredentials.deleteAll() }
}

enum LocalCredentials {
    static func query(_ host: String) -> [String: Any] {
        [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: "chiaki-ng.lan", kSecAttrAccount as String: host]
    }
    static func save(_ value: CBCredentials, host: String) throws {
        var copy = value
        let data = withUnsafeBytes(of: &copy) { Data($0) }
        var item = query(host); item[kSecValueData as String] = data
        let updated = SecItemUpdate(query(host) as CFDictionary, [kSecValueData as String: data, kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly] as CFDictionary)
        if updated == errSecItemNotFound {
            item[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
            guard SecItemAdd(item as CFDictionary, nil) == errSecSuccess else { throw CredentialError.save }
        } else if updated != errSecSuccess { throw CredentialError.save }
    }
    static func load(host: String) -> CBCredentials? {
        var item = query(host); item[kSecReturnData as String] = true; item[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        guard SecItemCopyMatching(item as CFDictionary, &result) == errSecSuccess, let data = result as? Data, data.count == MemoryLayout<CBCredentials>.size else { return nil }
        var credentials = CBCredentials(); _ = withUnsafeMutableBytes(of: &credentials) { data.copyBytes(to: $0) }; return credentials
    }
    // A missing item counts as deleted.
    static func delete(host: String) throws {
        let status = SecItemDelete(query(host) as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else { throw CredentialError.delete }
    }
    static func deleteAll() throws {
        let status = SecItemDelete([kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: "chiaki-ng.lan"] as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else { throw CredentialError.delete }
    }
    enum CredentialError: Error { case save, delete }
}
