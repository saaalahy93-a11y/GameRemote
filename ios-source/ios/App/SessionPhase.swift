import Foundation

enum ConsoleKind: String, Codable, CaseIterable, Hashable {
    case ps5, ps4
    var title: String { self == .ps5 ? "PlayStation 5" : "PlayStation 4" }
}

// Non-secret console metadata. `host` is the exact Keychain account string; never normalize it after saving.
struct SavedConsole: Codable, Identifiable, Hashable {
    let id: UUID
    var name: String
    let host: String
    var kind: ConsoleKind
}

struct RegistrationRequest {
    let name: String, host: String, kind: ConsoleKind, account: Data, pin: UInt32
}

// Field rules shared by the forms and the model. Nothing here touches the network.
enum RegistrationInput {
    static let hostLimit = 255
    static func host(_ text: String) -> String? {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        // Control characters (a pasted NUL above all) would make C see a shorter host than the one stored.
        let unsafe = trimmed.unicodeScalars.contains { $0.properties.isWhitespace || $0.properties.generalCategory == .control || $0.properties.generalCategory == .format }
        return trimmed.isEmpty || trimmed.utf8.count > hostLimit || unsafe ? nil : trimmed
    }
    static func account(_ text: String) -> Data? {
        guard let data = Data(base64Encoded: text.trimmingCharacters(in: .whitespacesAndNewlines)), data.count == 8 else { return nil }
        return data
    }
    static func digits(_ text: String, count: Int) -> Bool { text.utf8.count == count && text.utf8.allSatisfy { $0 >= 48 && $0 <= 57 } }
    static func pairingCode(_ text: String) -> UInt32? { digits(text, count: 8) ? UInt32(text) : nil }
    static func loginPIN(_ text: String) -> Data? { digits(text, count: 4) ? Data(text.utf8) : nil }
    static func name(_ text: String, host: String) -> String {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? host : String(trimmed.prefix(60))
    }
}

enum RegistrationFailure: Equatable {
    case startFailed(code: Int32)
    case rejected
    case credentialStorage
    case consoleListStorage
}

enum LoginPrompt: Equatable {
    case first
    case incorrect
    case submitFailed(code: Int32)
}

enum SessionEnd: Equatable {
    case quit(reason: Int32)
    case startFailed(code: Int32)
    case missingCredentials
}

// Published only from actual bridge outcomes on the lifecycle worker.
enum SessionPhase: Equatable {
    case idle
    case registering(host: String)
    case registered(SavedConsole)
    case registrationFailed(RegistrationFailure)
    case connecting(SavedConsole)
    case loginRequired(SavedConsole, LoginPrompt)
    case submittingLogin(SavedConsole)
    case streaming(SavedConsole)
    case stopping(SavedConsole?)
    case ended(SavedConsole, SessionEnd)
    // Native ownership is retained; only a repeated stop is safe.
    case cleanupFailed(SavedConsole?, code: Int32)

    var streamConsole: SavedConsole? {
        switch self {
        case .connecting(let console), .loginRequired(let console, _), .submittingLogin(let console), .streaming(let console), .ended(let console, _): return console
        case .stopping(let console), .cleanupFailed(let console, _): return console
        case .idle, .registering, .registered, .registrationFailed: return nil
        }
    }
    var allowsNewOperation: Bool {
        switch self {
        case .idle, .registered, .registrationFailed, .ended: return true
        default: return false
        }
    }
    var isStreaming: Bool { if case .streaming = self { return true }; return false }
}

enum LibraryIssue: Equatable {
    case loadFailed
    case renameFailed(name: String)
    case removeBlocked(name: String)
    case removeCredentialsFailed(name: String)
    // Credentials are already deleted; the console stays listed as unregistered.
    case removeListFailed(name: String)

    var message: String {
        switch self {
        case .loadFailed: return "Your saved consoles could not be read. Resetting deletes every saved console and its credentials from this device; you can then register again."
        case .renameFailed(let name): return "“\(name)” could not be renamed."
        case .removeBlocked(let name): return "Disconnect before removing “\(name)”."
        case .removeCredentialsFailed(let name): return "“\(name)” was not removed because its saved credentials could not be deleted. Unlock the device and try again."
        case .removeListFailed(let name): return "The credentials for “\(name)” were deleted, but it could not be removed from the list. It now needs registration; try removing it again."
        }
    }
}

// Mirrors CBQuitReason in GameRemoteBridge.h, which is statically checked against the core.
enum SessionCopy {
    static func message(for end: SessionEnd) -> String {
        switch end {
        case .missingCredentials: return "This console is not registered on this device. Set it up again with a new pairing code."
        case .startFailed: return "Could not start the connection. Check the console address and local network, then retry."
        case .quit(let reason):
            switch reason {
            case 1: return "The session was stopped."
            case 4: return "Remote Play is already in use on this console. Disconnect the other device, then retry."
            case 5: return "Remote Play stopped unexpectedly on the console. Retry in a moment."
            case 6: return "The console's Remote Play version is not supported by this app. Update the console or app, then retry."
            case 3, 8, 9: return "Could not connect. Check the console address and local network, then retry."
            case 11: return "The console disconnected."
            case 12: return "The console shut down or entered rest mode."
            default: return "The session ended unexpectedly. Check the console and local network, then retry."
            }
        }
    }
    static func detail(for end: SessionEnd) -> String? {
        switch end {
        case .missingCredentials: return nil
        case .startFailed(let code): return "Core error \(code)"
        case .quit(let reason): return "Quit reason \(reason)"
        }
    }
    static func message(for failure: RegistrationFailure) -> String {
        switch failure {
        case .startFailed: return "Registration could not start. Check the console address, then try again."
        case .rejected: return "Registration failed. Check the address and account ID, then enter a new pairing code."
        case .credentialStorage: return "The console accepted registration, but the credentials could not be saved to this device's Keychain. Unlock the device and register again with a new pairing code."
        case .consoleListStorage: return "Credentials were saved, but the console could not be added to your list. Register again with a new pairing code."
        }
    }
    static func detail(for failure: RegistrationFailure) -> String? {
        if case .startFailed(let code) = failure { return "Core error \(code)" }
        return nil
    }
    static let profile = "720p · 60 fps target · H.264"
}
