// Lifecycle tests for the real SessionModel against the scripted fake bridge (tests/fake).
// Credentials live in memory and the console list in a temporary directory: no Keychain, network or core.
import Foundation
import GameRemoteBridge
import FakeBridge

func check(_ condition: @autoclosure () -> Bool, _ message: String, line: UInt = #line) {
    if !condition() { fatalError("\(message) (line \(line))") }
}
// Publishing hops worker -> main; pump the main run loop until the model settles.
func wait(_ message: String, line: UInt = #line, until condition: () -> Bool) {
    let deadline = Date().addingTimeInterval(5)
    while !condition() { if Date() > deadline { fatalError("Timed out: \(message) (line \(line))") }; RunLoop.main.run(until: Date().addingTimeInterval(0.005)) }
}
func settle() { RunLoop.main.run(until: Date().addingTimeInterval(0.1)) }

final class MemoryCredentials: CredentialStore {
    enum Failure: Error { case scripted }
    private let lock = NSLock()
    private var items: [String: CBCredentials] = [:]
    var failSave = false, failDelete = false
    var hosts: Set<String> { lock.lock(); defer { lock.unlock() }; return Set(items.keys) }
    func save(_ value: CBCredentials, host: String) throws { lock.lock(); defer { lock.unlock() }; if failSave { throw Failure.scripted }; items[host] = value }
    func load(host: String) -> CBCredentials? { lock.lock(); defer { lock.unlock() }; return items[host] }
    func delete(host: String) throws { lock.lock(); defer { lock.unlock() }; if failDelete { throw Failure.scripted }; items[host] = nil }
    func deleteAll() throws { lock.lock(); defer { lock.unlock() }; if failDelete { throw Failure.scripted }; items.removeAll() }
}

let root = FileManager.default.temporaryDirectory.appendingPathComponent("gameremote-model-\(UUID().uuidString)")
try! FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
defer { try? FileManager.default.removeItem(at: root) }
func request(_ host: String, name: String = "Den", kind: ConsoleKind = .ps5) -> RegistrationRequest {
    RegistrationRequest(name: name, host: host, kind: kind, account: Data([1, 2, 3, 4, 5, 6, 7, 8]), pin: 1234567)
}
func makeModel(_ name: String, credentials: MemoryCredentials) -> SessionModel {
    fake_bridge_reset()
    return SessionModel(index: ConsoleIndex(url: root.appendingPathComponent(name).appendingPathComponent("consoles.json")), credentials: credentials)
}
func registerConsole(_ model: SessionModel, host: String, name: String = "Den") -> SavedConsole {
    model.register(request(host, name: name))
    wait("registration starts") { model.phase == .registering(host: host) }
    fake_finish_registration(0, 9)
    wait("registration completes") { if case .registered = model.phase { return true }; return false }
    guard case .registered(let console) = model.phase else { fatalError("unreachable") }
    return console
}

// MARK: Registration outcomes
do {
    let store = MemoryCredentials(), model = makeModel("registration", credentials: store)
    wait("initial library load") { model.libraryIssue == nil && model.consoles.isEmpty }
    let console = registerConsole(model, host: "192.168.1.20")
    check(console.host == "192.168.1.20" && console.name == "Den" && console.kind == .ps5, "registered console carries the request metadata")
    check(fake_bridge().pointee.last_pin == 1234567 && fake_bridge().pointee.last_ps5, "the bridge receives the request")
    check(store.load(host: "192.168.1.20")?.morning.0 == 9, "credentials are stored under the exact host")
    wait("library publishes") { model.consoles == [console] && model.registeredIDs == [console.id] }
    check(fake_bridge().pointee.live_registrations == 0, "the registration handle is destroyed after its callback")
    model.dismissRegistrationOutcome(); wait("outcome dismissed") { model.phase == .idle }

    model.register(request("10.0.0.9")); wait("second registration") { model.phase == .registering(host: "10.0.0.9") }
    fake_finish_registration(-1, 0)
    wait("rejection") { model.phase == .registrationFailed(.rejected) }
    check(store.hosts == ["192.168.1.20"] && model.consoles == [console], "a rejected registration saves nothing")

    fake_bridge().pointee.registration_start_result = 5
    model.register(request("10.0.0.9")); wait("start failure") { model.phase == .registrationFailed(.startFailed(code: 5)) }
    fake_bridge().pointee.registration_start_result = 0

    store.failSave = true
    model.register(request("10.0.0.9")); wait("registering") { model.phase == .registering(host: "10.0.0.9") }
    fake_finish_registration(0, 9)
    wait("credential storage failure") { model.phase == .registrationFailed(.credentialStorage) }
    settle(); check(model.consoles == [console], "a console whose credentials were not stored is never listed")
    store.failSave = false
    print("Registration success, rejection, start failure and credential-storage failure passed")
}

// MARK: Console list storage failure after credentials are saved
do {
    fake_bridge_reset()
    let blocker = root.appendingPathComponent("blocker"); try! Data().write(to: blocker)
    let store = MemoryCredentials()
    let model = SessionModel(index: ConsoleIndex(url: blocker.appendingPathComponent("consoles.json")), credentials: store)
    model.register(request("10.0.0.5")); wait("registering") { model.phase == .registering(host: "10.0.0.5") }
    fake_finish_registration(0, 9)
    wait("list storage failure") { model.phase == .registrationFailed(.consoleListStorage) }
    settle(); check(model.consoles.isEmpty, "an unlisted console is not offered for connection")
    check(store.hosts.isEmpty, "new credentials are not left behind for an unlisted console")
    print("Console-list storage failure passed")
}

// MARK: Cancellation and stale callbacks
do {
    let store = MemoryCredentials(), model = makeModel("stale", credentials: store)
    model.register(request("10.0.0.7")); wait("registering") { model.phase == .registering(host: "10.0.0.7") }
    // A success callback that fires while the registration is being cancelled is queued behind the stop.
    fake_bridge().pointee.emit_during_destroy = true
    model.stop(); wait("cancelled") { model.phase == .idle }
    settle()
    check(model.phase == .idle && store.hosts.isEmpty && model.consoles.isEmpty, "a cancelled registration's late callback saves nothing")
    fake_bridge().pointee.emit_during_destroy = false
    check(fake_bridge().pointee.live_registrations == 0, "cancel destroys the registration")

    let console = registerConsole(model, host: "10.0.0.7")
    model.connect(console); wait("connecting") { model.phase == .connecting(console) }
    fake_emit_event(1, 0); wait("streaming") { model.phase == .streaming(console) }
    // The core reports quit(stopped) from inside our own stop; it must not resurface as a session error.
    fake_bridge().pointee.emit_during_destroy = true
    model.stop(); wait("stopped") { model.phase == .idle }
    settle(); check(model.phase == .idle && fake_bridge().pointee.live_sessions == 0, "a self-inflicted quit event is ignored after stop")
    print("Registration cancel, stale registration callback and stale quit event passed")
}

// MARK: Session lifecycle, login PIN and recovery
do {
    let store = MemoryCredentials(), model = makeModel("session", credentials: store)
    let console = registerConsole(model, host: "192.168.1.30")
    let unregistered = SavedConsole(id: UUID(), name: "Ghost", host: "10.9.9.9", kind: .ps4)
    model.connect(unregistered); wait("missing credentials") { model.phase == .ended(unregistered, .missingCredentials) }
    check(fake_bridge().pointee.session_creates == 0, "no session is created without credentials")

    fake_bridge().pointee.session_create_result = 3
    model.connect(console); wait("create failure") { model.phase == .ended(console, .startFailed(code: 3)) }
    fake_bridge().pointee.session_create_result = 0; fake_bridge().pointee.session_start_result = 4
    model.connect(console); wait("start failure") { model.phase == .ended(console, .startFailed(code: 4)) }
    check(fake_bridge().pointee.live_sessions == 0, "a session that failed to start is destroyed")
    fake_bridge().pointee.session_start_result = 0

    model.connect(console); wait("connecting") { model.phase == .connecting(console) }
    check(String(cString: withUnsafeBytes(of: fake_bridge().pointee.last_host) { Array($0) }) == "192.168.1.30", "the session targets the saved host")
    let creates = fake_bridge().pointee.session_creates
    model.connect(console); model.register(request("10.0.0.1")); settle()
    check(fake_bridge().pointee.session_creates == creates && fake_bridge().pointee.registration_starts == 1 && model.phase == .connecting(console), "operations are rejected while a session is owned")

    fake_emit_event(3, 0); wait("login requested") { model.phase == .loginRequired(console, .first) }
    model.submitLoginPIN(Data("0042".utf8)); wait("pin submitted") { model.phase == .submittingLogin(console) }
    check(fake_bridge().pointee.login_pins == 1, "the PIN reaches the bridge once")
    fake_emit_event(3, 1); wait("pin rejected") { model.phase == .loginRequired(console, .incorrect) }
    model.submitLoginPIN(Data("12".utf8)); settle()
    check(fake_bridge().pointee.login_pins == 1 && model.phase == .loginRequired(console, .incorrect), "a malformed PIN is not sent")
    model.submitLoginPIN(Data("1234".utf8)); wait("pin resubmitted") { model.phase == .submittingLogin(console) }
    fake_emit_event(1, 0); wait("streaming") { model.phase == .streaming(console) }

    fake_emit_event(2, Int32(CB_QUIT_IN_USE.rawValue)); wait("quit") { model.phase == .ended(console, .quit(reason: 4)) }
    check(fake_bridge().pointee.live_sessions == 0, "a quit tears the session down before it is reported")
    model.dismissRegistrationOutcome(); settle(); check(model.phase == .ended(console, .quit(reason: 4)), "a registration dismissal cannot hide a session error")
    model.dismissSessionOutcome(); wait("dismissed") { model.phase == .idle }
    print("Missing credentials, start failures, busy rejection, login-PIN retry and quit recovery passed")
}

// MARK: Failed cleanup keeps ownership
do {
    let store = MemoryCredentials(), model = makeModel("cleanup", credentials: store)
    let console = registerConsole(model, host: "192.168.1.40")
    let other = registerConsoleAfterDismiss(model, host: "192.168.1.41")
    model.connect(console); wait("connecting") { model.phase == .connecting(console) }
    fake_emit_event(1, 0); wait("streaming") { model.phase == .streaming(console) }
    fake_bridge().pointee.session_destroy_failures = 2; fake_bridge().pointee.destroy_error = 6
    model.stop(); wait("cleanup failed") { model.phase == .cleanupFailed(console, code: 6) }
    check(fake_bridge().pointee.live_sessions == 1, "the session stays owned after a failed stop")
    let creates = fake_bridge().pointee.session_creates
    model.connect(other); model.remove(console); model.dismissSessionOutcome()
    wait("removal blocked") { model.libraryIssue == .removeBlocked(name: console.name) }
    settle()
    check(fake_bridge().pointee.session_creates == creates && model.phase == .cleanupFailed(console, code: 6), "no reconnect or dismissal while cleanup is pending")
    // Late core events and a PIN submission must not repaint a half-closed session as live.
    let pins = fake_bridge().pointee.login_pins
    fake_emit_event(1, 0); fake_emit_event(3, 0); model.submitLoginPIN(Data("1234".utf8)); settle()
    check(model.phase == .cleanupFailed(console, code: 6) && fake_bridge().pointee.login_pins == pins, "late events cannot leave the cleanup-failed state")
    check(store.hosts.contains(console.host) && model.consoles.contains(console), "a console in use is not removed")
    model.stop(); wait("second failure") { fake_bridge().pointee.session_destroy_failures == 0 }
    settle(); check(model.phase == .cleanupFailed(console, code: 6), "a repeated failure is still reported")
    model.stop(); wait("cleanup succeeds") { model.phase == .idle }
    check(fake_bridge().pointee.live_sessions == 0, "the retry releases the session")
    model.connect(other); wait("reconnect allowed") { model.phase == .connecting(other) }
    // A quit whose teardown fails must not be presented as a finished session.
    fake_bridge().pointee.session_destroy_failures = 1
    fake_emit_event(2, 11); wait("quit with failed cleanup") { model.phase == .cleanupFailed(other, code: 6) }
    model.stop(); wait("released") { model.phase == .idle }
    print("Failed stop retention, blocked reconnect/removal and safe retry passed")
}
func registerConsoleAfterDismiss(_ model: SessionModel, host: String) -> SavedConsole {
    model.dismissRegistrationOutcome(); wait("dismissed") { model.phase == .idle }
    let console = registerConsole(model, host: host, name: "Second")
    model.dismissRegistrationOutcome(); wait("dismissed") { model.phase == .idle }
    return console
}

// MARK: Touch input through the single poll
do {
    let store = MemoryCredentials(), model = makeModel("input", credentials: store)
    let console = registerConsole(model, host: "192.168.1.50")
    model.connect(console); wait("connecting") { model.phase == .connecting(console) }
    fake_emit_event(1, 0); wait("streaming") { model.phase == .streaming(console) }
    model.input.setButton(.cross, pressed: true); model.input.setTrigger(left: false, pressed: true); model.input.setStick(left: true, x: -1, y: 0)
    let before = fake_bridge().pointee.controller_submissions
    wait("polls deliver input") { fake_bridge().pointee.controller_submissions >= before + 10 }
    let held = fake_bridge().pointee.last_controller
    // A physical controller attached to this Mac may add input; the touch contribution must still be present.
    check(held.buttons & PadButton.cross.rawValue != 0 && held.r2 == 255 && held.lx == -32767, "held touch input is still present after many polls")
    model.input.setButton(.cross, pressed: false)
    let released = fake_bridge().pointee.controller_submissions
    wait("release delivered") { fake_bridge().pointee.controller_submissions >= released + 3 }
    check(fake_bridge().pointee.last_controller.r2 == 255, "other held controls stay held")
    var completed = false
    model.stop(then: { completed = true }); wait("stopped") { model.phase == .idle && completed }
    check(model.input.merged(with: PadState()) == PadState(), "stopping releases every touch control")
    let idleSubmissions = fake_bridge().pointee.controller_submissions
    completed = false; model.stop(then: { completed = true }); wait("idle stop still completes") { completed }
    settle(); check(fake_bridge().pointee.controller_submissions == idleSubmissions, "no input is submitted without a session")
    model.input.setButton(.ps, pressed: true)
    model.connect(console); wait("connecting") { model.phase == .connecting(console) }
    fake_emit_event(2, 12); wait("ended") { model.phase == .ended(console, .quit(reason: 12)) }
    check(model.input.merged(with: PadState()) == PadState(), "a console-side quit releases every touch control")
    print("Touch input delivery across polls and release on stop/quit passed")
}

// MARK: Removal, rename and reset
do {
    let store = MemoryCredentials(), model = makeModel("library", credentials: store)
    let console = registerConsole(model, host: "192.168.1.60")
    model.dismissRegistrationOutcome(); wait("dismissed") { model.phase == .idle }
    model.rename(console, to: "  Lounge  "); wait("renamed") { model.consoles.first?.name == "Lounge" }
    check(model.consoles.first?.id == console.id && model.consoles.first?.host == console.host, "rename keeps identity and Keychain key")

    store.failDelete = true
    model.remove(console); wait("credential delete failure") { model.libraryIssue == .removeCredentialsFailed(name: console.name) }
    settle(); check(model.consoles.count == 1 && model.registeredIDs == [console.id], "a failed credential delete leaves the console intact")
    store.failDelete = false; model.libraryIssue = nil

    let reopened = SessionModel(index: ConsoleIndex(url: root.appendingPathComponent("library/consoles.json")), credentials: store)
    wait("reload") { reopened.consoles.count == 1 && reopened.registeredIDs == [console.id] }
    try! store.delete(host: console.host); reopened.reloadLibrary()
    wait("credentials gone") { reopened.registeredIDs.isEmpty && reopened.consoles.count == 1 }
    print("A listed console without credentials is shown as unregistered")
    try! store.save(CBCredentials(), host: console.host)

    model.remove(model.consoles[0]); wait("removed") { model.consoles.isEmpty }
    check(store.hosts.isEmpty && model.libraryIssue == nil, "removal deletes credentials and the entry")

    let second = registerConsole(model, host: "192.168.1.61")
    try! Data("corrupt".utf8).write(to: root.appendingPathComponent("library/consoles.json"))
    model.reloadLibrary(); wait("load failure") { model.libraryIssue == .loadFailed }
    model.libraryIssue = nil
    model.remove(second); wait("list removal failure") { model.libraryIssue == .removeListFailed(name: second.name) }
    check(!store.hosts.contains(second.host), "credentials are deleted before the list entry")
    try! store.save(CBCredentials(), host: "orphan"); model.libraryIssue = nil
    model.resetLibrary(); wait("reset") { store.hosts.isEmpty }
    model.reloadLibrary(); settle(); check(model.libraryIssue == nil && model.consoles.isEmpty, "reset clears credentials and restores a readable list")
    print("Rename, removal partial failures, unreadable list and reset passed")
}
print("SessionModel lifecycle tests passed (fake bridge, in-memory credentials)")
