import Foundation

// Header retention, queue capacity and recovery live under one lock. No header work is queued.
final class VideoAdmission {
    struct Configuration { let version: UInt64; let sps: Data; let pps: Data }
    struct Frame { let configuration: Configuration; let nals: [Data]; let isIDR: Bool; let recoveryVersion: UInt64 }
    enum Result { case header, rejected, frame(Frame) }
    private let lock = NSLock()
    private let capacity: Int
    private var pending = 0
    private var configuration: Configuration?
    private var pendingSPS: Data?, pendingPPS: Data?
    private var version: UInt64 = 0, recoveryVersion: UInt64 = 0
    private var needsIDR = true
    init(capacity: Int = 2) { precondition(capacity > 0); self.capacity = capacity }
    func admit(_ nals: [Data]) -> Result {
        lock.lock(); defer { lock.unlock() }
        for nal in nals {
            if nal.first.map({ $0 & 31 == 7 }) == true { pendingSPS = nal }
            if nal.first.map({ $0 & 31 == 8 }) == true { pendingPPS = nal }
        }
        if let sps = pendingSPS, let pps = pendingPPS {
            if configuration?.sps != sps || configuration?.pps != pps {
                version += 1; recoveryVersion += 1; needsIDR = true
                configuration = Configuration(version: version, sps: sps, pps: pps)
            }
            pendingSPS = nil; pendingPPS = nil
        }
        let hasSlice = nals.contains { $0.first.map { let type = $0 & 31; return type == 1 || type == 5 } ?? false }
        guard hasSlice else { return .header }
        let isIDR = nals.contains { $0.first.map { $0 & 31 == 5 } ?? false }
        guard let configuration else { recoveryVersion += 1; needsIDR = true; return .rejected }
        guard pending < capacity else { recoveryVersion += 1; needsIDR = true; return .rejected }
        guard !needsIDR || isIDR else { return .rejected }
        pending += 1
        return .frame(Frame(configuration: configuration, nals: nals, isIDR: isIDR, recoveryVersion: recoveryVersion))
    }
    func finish(_ frame: Frame) { lock.lock(); defer { lock.unlock() }; precondition(pending > 0); pending -= 1 }
    func canDisplay(_ frame: Frame) -> Bool {
        lock.lock(); defer { lock.unlock() }
        return configuration?.version == frame.configuration.version && (!needsIDR || frame.isIDR)
    }
    func drop(_ frame: Frame) {
        lock.lock(); defer { lock.unlock() }
        guard configuration?.version == frame.configuration.version else { return }
        recoveryVersion += 1; needsIDR = true
    }
    // Enqueue and recovery completion are atomic with respect to new headers/drops.
    @discardableResult func display(_ frame: Frame, enqueue: () -> Void) -> Bool {
        lock.lock(); defer { lock.unlock() }
        guard configuration?.version == frame.configuration.version && (!needsIDR || frame.isIDR) else { return false }
        enqueue()
        if frame.isIDR && frame.recoveryVersion == recoveryVersion { needsIDR = false }
        return true
    }
    func reset() {
        lock.lock(); defer { lock.unlock() }
        configuration = nil; pendingSPS = nil; pendingPPS = nil
        version += 1; recoveryVersion += 1; needsIDR = true
        // Outstanding queued frames still own capacity until their finish calls.
    }
}

// Called only from the audio worker. Publish cached format after successful startup.
final class StartupCache<Key: Equatable, Value> {
    private var key: Key?
    private(set) var value: Value?
    func ensure(_ requested: Key, running: Bool, reset: () -> Void, start: () throws -> Value) throws -> Value {
        if key == requested, running, let value { return value }
        clear(); reset()
        do {
            let started = try start()
            key = requested; value = started
            return started
        } catch { clear(); reset(); throw error }
    }
    func clear() { key = nil; value = nil }
}
struct AudioConfiguration: Equatable { let channels: UInt32; let rate: UInt32 }
