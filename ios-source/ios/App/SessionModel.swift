import Foundation
import Combine
import GameController
import GameRemoteBridge

fileprivate struct OperationTarget {
    let name: String, host: String, kind: ConsoleKind
    let console: SavedConsole? // nil while registering
}
fileprivate final class CallbackContext {
    let model: SessionModel, target: OperationTarget
    init(model: SessionModel, target: OperationTarget) { self.model = model; self.target = target }
}
private func owner(_ context: UnsafeMutableRawPointer?) -> CallbackContext { Unmanaged<CallbackContext>.fromOpaque(context!).takeUnretainedValue() }
private let eventCallback: @convention(c) (UnsafeMutableRawPointer?, Int32, Int32) -> Void = { context, kind, detail in
    let token = owner(context), model = token.model
    model.worker.async {
        guard model.isCurrent(token) else { return }
        model.handleEvent(kind: kind, detail: detail)
    }
}
private let videoCallback: @convention(c) (UnsafeMutableRawPointer?, UnsafePointer<UInt8>?, Int) -> Bool = { context, bytes, size in
    guard let bytes else { return false }; return owner(context).model.media.video(Data(bytes: bytes, count: size))
}
private let audioCallback: @convention(c) (UnsafeMutableRawPointer?, UnsafePointer<Int16>?, Int, UInt32, UInt32) -> Void = { context, samples, frames, channels, rate in
    guard let samples else { return }; owner(context).model.media.audio(Data(bytes: samples, count: frames * Int(channels) * 2), frames: frames, channels: channels, rate: rate)
}
private let registrationCallback: @convention(c) (UnsafeMutableRawPointer?, Int32, UnsafePointer<CBCredentials>?) -> Void = { context, result, credentials in
    let token = owner(context), model = token.model; let copied = credentials?.pointee
    // Complete/join on our queue, never on the registration callback thread.
    model.worker.async {
        guard model.isCurrent(token) else { return }
        model.finishRegistration(token.target, result: result, credentials: copied)
    }
}

final class SessionModel: ObservableObject {
    @Published private(set) var phase: SessionPhase = .idle
    @Published private(set) var consoles: [SavedConsole] = []
    // Consoles whose credentials can currently be read from the Keychain.
    @Published private(set) var registeredIDs: Set<UUID> = []
    @Published private(set) var mediaIssue: String?
    @Published private(set) var controllerName: String?
    @Published var libraryIssue: LibraryIssue?
    let media = Media()
    let input = InputAggregator()
    fileprivate let worker = DispatchQueue(label: "chiaki.lifecycle")
    // Worker-queue state.
    fileprivate var session: OpaquePointer?, registration: OpaquePointer?
    private var target: OperationTarget?
    private var current: SessionPhase = .idle
    private var context: UnsafeMutableRawPointer?
    private var currentContext: CallbackContext?
    private let index: ConsoleIndex?
    private let credentials: CredentialStore
    private let inputSlot = DispatchSemaphore(value: 1)
    private var timer: Timer?
    private var observers: [NSObjectProtocol] = []

    init(index: ConsoleIndex? = (try? ConsoleIndex.defaultURL()).map(ConsoleIndex.init(url:)), credentials: CredentialStore = KeychainCredentials()) {
        self.index = index; self.credentials = credentials
        media.failure = { [weak self] message in self?.mediaIssue = message }
        // Common modes keep the 60 Hz poll running while UIKit tracks touches.
        let timer = Timer(timeInterval: 1.0 / 60.0, repeats: true) { [weak self] _ in self?.pollInput() }
        RunLoop.main.add(timer, forMode: .common); self.timer = timer
        for name in [Notification.Name.GCControllerDidConnect, .GCControllerDidDisconnect] {
            observers.append(NotificationCenter.default.addObserver(forName: name, object: nil, queue: .main) { [weak self] _ in self?.refreshController() })
        }
        refreshController()
        reloadLibrary()
    }

    // MARK: Worker-queue lifecycle

    fileprivate func publish(_ value: SessionPhase) { current = value; DispatchQueue.main.async { self.phase = value } }
    private func retainContext(_ target: OperationTarget) -> UnsafeMutableRawPointer {
        if let context { return context }
        self.target = target
        let token = CallbackContext(model: self, target: target); currentContext = token
        let pointer = Unmanaged.passRetained(token).toOpaque(); context = pointer; return pointer
    }
    fileprivate func isCurrent(_ token: CallbackContext) -> Bool { currentContext === token }
    private func releaseContextIfIdle() {
        if session == nil && registration == nil, let context { self.context = nil; currentContext = nil; target = nil; Unmanaged<CallbackContext>.fromOpaque(context).release() }
    }
    // Returns false when stop/join failed and native ownership is retained for a retry.
    private func teardown() -> Bool {
        if let registration { _ = cb_registration_destroy(registration); self.registration = nil }
        if let session {
            let result = cb_session_destroy(session)
            guard result == 0 else { publish(.cleanupFailed(target?.console, code: result)); return false }
            self.session = nil
        }
        DispatchQueue.main.async { self.mediaIssue = nil }
        media.stop(); input.releaseTouch()
        releaseContextIfIdle()
        return true
    }
    fileprivate func handleEvent(kind: Int32, detail: Int32) {
        guard let console = target?.console else { return }
        // After a failed stop the session is half-closed: only a quit may move it on.
        if case .cleanupFailed = current, kind != 2 { return }
        switch kind {
        case 1: publish(.streaming(console))
        case 3: publish(.loginRequired(console, detail != 0 ? .incorrect : .first))
        case 2:
            publish(.stopping(console))
            if teardown() { publish(.ended(console, .quit(reason: detail))) }
        default: break
        }
    }
    fileprivate func finishRegistration(_ target: OperationTarget, result: Int32, credentials received: CBCredentials?) {
        defer { releaseContextIfIdle() }
        if let registration { _ = cb_registration_destroy(registration); self.registration = nil }
        guard result == 0, let received else { publish(.registrationFailed(.rejected)); return }
        let replacing = credentials.load(host: target.host) != nil
        do { try credentials.save(received, host: target.host) } catch { publish(.registrationFailed(.credentialStorage)); return }
        // Listed only after the credentials are stored; new keys are not left behind for an unlisted console.
        guard let saved = try? index?.save(name: target.name, host: target.host, kind: target.kind) else {
            if !replacing { try? credentials.delete(host: target.host) }
            publish(.registrationFailed(.consoleListStorage)); return
        }
        publishLibrary(saved.all)
        publish(.registered(saved.console))
    }

    // MARK: Operations (callable from the main thread)

    func register(_ request: RegistrationRequest) {
        worker.async {
            guard self.session == nil && self.registration == nil else { return }
            let context = self.retainContext(OperationTarget(name: request.name, host: request.host, kind: request.kind, console: nil))
            let result = request.account.withUnsafeBytes { raw in request.host.withCString { cb_registration_start($0, request.kind == .ps5, raw.bindMemory(to: UInt8.self).baseAddress, request.pin, registrationCallback, context, &self.registration) } }
            self.publish(result == 0 ? .registering(host: request.host) : .registrationFailed(.startFailed(code: result)))
            self.releaseContextIfIdle()
        }
    }
    func connect(_ console: SavedConsole) {
        worker.async {
            guard self.session == nil && self.registration == nil else { return }
            guard var keys = self.credentials.load(host: console.host) else {
                self.publish(.ended(console, .missingCredentials)); self.publishLibrary(self.consolesSnapshot()); return
            }
            let target = OperationTarget(name: console.name, host: console.host, kind: console.kind, console: console)
            let callbacks = CBCallbacks(event: eventCallback, video: videoCallback, audio: audioCallback, context: self.retainContext(target))
            var result = console.host.withCString { cb_session_create($0, console.kind == .ps5, &keys, callbacks, &self.session) }
            if result == 0, let session = self.session { result = cb_session_start(session) }
            if result != 0, let session = self.session {
                let cleanup = cb_session_destroy(session)
                if cleanup == 0 { self.session = nil } else { self.publish(.cleanupFailed(console, code: cleanup)); return }
            }
            self.publish(result == 0 ? .connecting(console) : .ended(console, .startFailed(code: result)))
            self.releaseContextIfIdle()
        }
    }
    // Stops a session or cancels a registration. Without native work in flight this is a no-op.
    func stop(then completion: (() -> Void)? = nil) {
        input.releaseTouch()
        worker.async {
            defer { if let completion { DispatchQueue.main.async(execute: completion) } }
            guard self.session != nil || self.registration != nil else { return }
            self.publish(.stopping(self.target?.console))
            if self.teardown() { self.publish(.idle) }
        }
    }
    func submitLoginPIN(_ pin: Data) {
        worker.async {
            guard case .loginRequired = self.current, let session = self.session, let console = self.target?.console, pin.count == 4 else { return }
            let result = pin.withUnsafeBytes { cb_session_login_pin(session, $0.bindMemory(to: UInt8.self).baseAddress, pin.count) }
            self.publish(result == 0 ? .submittingLogin(console) : .loginRequired(console, .submitFailed(code: result)))
        }
    }
    func dismissRegistrationOutcome() {
        worker.async { switch self.current { case .registered, .registrationFailed: self.publish(.idle); default: break } }
    }
    func dismissSessionOutcome() {
        worker.async { if case .ended = self.current { self.publish(.idle) } }
    }

    // MARK: Saved consoles

    private func consolesSnapshot() -> [SavedConsole] { (try? index?.load()) ?? [] }
    private func publishLibrary(_ consoles: [SavedConsole]) {
        let registered = Set(consoles.filter { credentials.load(host: $0.host) != nil }.map(\.id))
        DispatchQueue.main.async { self.consoles = consoles; self.registeredIDs = registered }
    }
    private func report(_ issue: LibraryIssue) { DispatchQueue.main.async { self.libraryIssue = issue } }
    func reloadLibrary() {
        worker.async {
            guard let consoles = try? self.index?.load() else { self.report(.loadFailed); return }
            self.publishLibrary(consoles)
        }
    }
    func rename(_ console: SavedConsole, to name: String) {
        let name = RegistrationInput.name(name, host: console.host)
        worker.async {
            guard let consoles = try? self.index?.rename(id: console.id, name: name) else { self.report(.renameFailed(name: console.name)); return }
            self.publishLibrary(consoles)
        }
    }
    // Credentials first: a console is never left listed as registered without its keys, or unlisted with them.
    func remove(_ console: SavedConsole) {
        worker.async {
            guard self.session == nil && self.registration == nil else { self.report(.removeBlocked(name: console.name)); return }
            do { try self.credentials.delete(host: console.host) } catch { self.report(.removeCredentialsFailed(name: console.name)); return }
            guard let consoles = try? self.index?.remove(id: console.id) else {
                self.report(.removeListFailed(name: console.name)); self.publishLibrary(self.consolesSnapshot()); return
            }
            self.publishLibrary(consoles)
        }
    }
    // Recovery for an unreadable list: deletes every saved credential, then starts an empty list.
    func resetLibrary() {
        worker.async {
            guard self.session == nil && self.registration == nil, let index = self.index else { self.report(.loadFailed); return }
            do { try self.credentials.deleteAll(); try index.reset(); self.publishLibrary([]) } catch { self.report(.loadFailed) }
        }
    }

    // MARK: Controller input

    private func refreshController() {
        controllerName = GCController.controllers().first { $0.extendedGamepad != nil }.map { $0.vendorName ?? "Game controller" }
    }
    private static func physicalState() -> PadState {
        var state = PadState()
        guard let pad = GCController.controllers().lazy.compactMap({ $0.extendedGamepad }).first else { return state }
        let touchpad = (pad as? GCDualSenseGamepad)?.touchpadButton ?? (pad as? GCDualShockGamepad)?.touchpadButton
        let buttons: [(GCControllerButtonInput?, PadButton)] = [
            (pad.buttonA, .cross), (pad.buttonB, .circle), (pad.buttonX, .square), (pad.buttonY, .triangle),
            (pad.dpad.left, .dpadLeft), (pad.dpad.right, .dpadRight), (pad.dpad.up, .dpadUp), (pad.dpad.down, .dpadDown),
            (pad.leftShoulder, .l1), (pad.rightShoulder, .r1), (pad.leftThumbstickButton, .l3), (pad.rightThumbstickButton, .r3),
            (pad.buttonMenu, .options), (pad.buttonOptions, .create), (touchpad, .touchpad), (pad.buttonHome, .ps)]
        for (button, mapped) in buttons where button?.isPressed == true { state.buttons |= mapped.rawValue }
        state.l2 = UInt8(max(0, min(1, pad.leftTrigger.value)) * 255); state.r2 = UInt8(max(0, min(1, pad.rightTrigger.value)) * 255)
        state.lx = PadState.axis(Double(pad.leftThumbstick.xAxis.value)); state.ly = PadState.axis(Double(-pad.leftThumbstick.yAxis.value))
        state.rx = PadState.axis(Double(pad.rightThumbstick.xAxis.value)); state.ry = PadState.axis(Double(-pad.rightThumbstick.yAxis.value))
        return state
    }
    // The only writer of controller state: physical and touch input are merged here, at most one submission pending.
    private func pollInput() {
        guard phase.streamConsole != nil else { return }
        let merged = input.merged(with: Self.physicalState())
        guard inputSlot.wait(timeout: .now()) == .success else { return }
        let state = CBController(buttons: merged.buttons, l2: merged.l2, r2: merged.r2, lx: merged.lx, ly: merged.ly, rx: merged.rx, ry: merged.ry)
        worker.async { defer { self.inputSlot.signal() }; if let session = self.session { _ = cb_session_controller(session, state) } }
    }
}
