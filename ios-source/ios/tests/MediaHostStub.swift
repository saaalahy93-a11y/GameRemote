// Compile-only collaborator for macOS checking of lifecycle/Keychain/controller code.
// Excluded from the app target; this is not evidence of native media playback.
import Foundation
final class Media {
    var failure: ((String) -> Void)?
    func video(_ data: Data) -> Bool { false }
    func audio(_ data: Data, frames: Int, channels: UInt32, rate: UInt32) {}
    func stop() {}
}
