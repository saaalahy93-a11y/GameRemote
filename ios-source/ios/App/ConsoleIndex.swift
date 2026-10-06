import Foundation

// File-backed list of saved consoles. Holds names, addresses and console types only;
// pairing keys stay in the Keychain under the exact `host` string.
final class ConsoleIndex {
    enum Failure: Error { case unreadable, unwritable }
    private struct Document: Codable { var version: Int; var consoles: [SavedConsole] }
    private static let currentVersion = 1
    private let url: URL
    private let lock = NSLock()

    init(url: URL) { self.url = url }

    static func defaultURL() throws -> URL {
        let base = try FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
        return base.appendingPathComponent("GameRemote", isDirectory: true).appendingPathComponent("consoles.json")
    }

    func load() throws -> [SavedConsole] { lock.lock(); defer { lock.unlock() }; return try read() }

    // One entry per exact host. Re-registering keeps the entry's identity and updates name/type.
    func save(name: String, host: String, kind: ConsoleKind) throws -> (console: SavedConsole, all: [SavedConsole]) {
        lock.lock(); defer { lock.unlock() }
        var consoles = try read()
        let console: SavedConsole
        // Byte-exact, like the Keychain account: Unicode-equivalent spellings are different hosts.
        if let position = consoles.firstIndex(where: { $0.host.utf8.elementsEqual(host.utf8) }) {
            console = SavedConsole(id: consoles[position].id, name: name, host: host, kind: kind)
            consoles[position] = console
        } else {
            console = SavedConsole(id: UUID(), name: name, host: host, kind: kind)
            consoles.append(console)
        }
        try write(consoles)
        return (console, consoles)
    }

    func rename(id: UUID, name: String) throws -> [SavedConsole] {
        lock.lock(); defer { lock.unlock() }
        var consoles = try read()
        guard let position = consoles.firstIndex(where: { $0.id == id }) else { return consoles }
        consoles[position].name = name
        try write(consoles)
        return consoles
    }

    func remove(id: UUID) throws -> [SavedConsole] {
        lock.lock(); defer { lock.unlock() }
        let consoles = try read().filter { $0.id != id }
        try write(consoles)
        return consoles
    }

    // Explicit user recovery only: replaces an unreadable file with an empty list.
    func reset() throws { lock.lock(); defer { lock.unlock() }; try write([]) }

    private func read() throws -> [SavedConsole] {
        guard FileManager.default.fileExists(atPath: url.path) else { return [] }
        // An unreadable or newer file is reported, never silently replaced.
        guard let data = try? Data(contentsOf: url), let document = try? JSONDecoder().decode(Document.self, from: data),
              document.version == Self.currentVersion,
              document.consoles.allSatisfy({ RegistrationInput.host($0.host) == $0.host }) else { throw Failure.unreadable }
        return document.consoles
    }

    private func write(_ consoles: [SavedConsole]) throws {
        do {
            var directory = url.deletingLastPathComponent()
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            // Credentials never leave this device, so a restored list would only show consoles without keys.
            var values = URLResourceValues(); values.isExcludedFromBackup = true
            try? directory.setResourceValues(values)
            let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys]
            try encoder.encode(Document(version: Self.currentVersion, consoles: consoles)).write(to: url, options: .atomic)
        } catch { throw Failure.unwritable }
    }
}
