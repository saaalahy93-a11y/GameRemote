import Foundation

// Bit values follow the core controller button mask passed through CBController.buttons.
enum PadButton: UInt32, CaseIterable {
    case cross = 1, circle = 2, square = 4, triangle = 8
    case dpadLeft = 16, dpadRight = 32, dpadUp = 64, dpadDown = 128
    case l1 = 256, r1 = 512, l3 = 1024, r3 = 2048
    case options = 4096, create = 8192, touchpad = 16384, ps = 32768
}

struct PadState: Equatable {
    var buttons: UInt32 = 0
    var l2: UInt8 = 0, r2: UInt8 = 0
    var lx: Int16 = 0, ly: Int16 = 0, rx: Int16 = 0, ry: Int16 = 0

    static func axis(_ value: Double) -> Int16 { Int16((max(-1, min(1, value)) * 32767).rounded()) }
}

enum PadGeometry {
    // Eight sectors around the centre: an axis engages once it is at least a third of the other.
    static func directions(dx: Double, dy: Double, deadZone: Double) -> UInt32 {
        guard max(abs(dx), abs(dy)) >= deadZone else { return 0 }
        var held: UInt32 = 0
        if abs(dx) * 3 >= abs(dy) { held |= (dx < 0 ? PadButton.dpadLeft : PadButton.dpadRight).rawValue }
        if abs(dy) * 3 >= abs(dx) { held |= (dy < 0 ? PadButton.dpadUp : PadButton.dpadDown).rawValue }
        return held
    }
}

// Touch controls write here; the single 60 Hz poll reads the merged state.
// Nothing else submits controller input, so a poll can never overwrite a held touch.
final class InputAggregator {
    private let lock = NSLock()
    private var touch = PadState()

    func setButton(_ button: PadButton, pressed: Bool) {
        lock.lock(); defer { lock.unlock() }
        if pressed { touch.buttons |= button.rawValue } else { touch.buttons &= ~button.rawValue }
    }
    func setTrigger(left: Bool, pressed: Bool) {
        lock.lock(); defer { lock.unlock() }
        if left { touch.l2 = pressed ? 255 : 0 } else { touch.r2 = pressed ? 255 : 0 }
    }
    // x right-positive, y down-positive, each in -1...1; clamped to the unit circle.
    func setStick(left: Bool, x: Double, y: Double) {
        let length = (x * x + y * y).squareRoot(), scale = length > 1 ? 1 / length : 1
        let ax = PadState.axis(x * scale), ay = PadState.axis(y * scale)
        lock.lock(); defer { lock.unlock() }
        if left { touch.lx = ax; touch.ly = ay } else { touch.rx = ax; touch.ry = ay }
    }
    func releaseTouch() { lock.lock(); defer { lock.unlock() }; touch = PadState() }

    func merged(with physical: PadState) -> PadState {
        lock.lock(); let touch = self.touch; lock.unlock()
        return Self.merge(physical, touch)
    }

    // Buttons combine, triggers take the stronger pull, each stick follows whichever source is deflected further.
    static func merge(_ a: PadState, _ b: PadState) -> PadState {
        var result = PadState()
        result.buttons = a.buttons | b.buttons
        result.l2 = max(a.l2, b.l2); result.r2 = max(a.r2, b.r2)
        func magnitude(_ x: Int16, _ y: Int16) -> Int { Int(x) * Int(x) + Int(y) * Int(y) }
        if magnitude(b.lx, b.ly) > magnitude(a.lx, a.ly) { result.lx = b.lx; result.ly = b.ly } else { result.lx = a.lx; result.ly = a.ly }
        if magnitude(b.rx, b.ry) > magnitude(a.rx, a.ry) { result.rx = b.rx; result.ry = b.ry } else { result.rx = a.rx; result.ry = a.ry }
        return result
    }
}
