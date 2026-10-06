import Foundation
let source = Data([0,0,0,1,0x67,1,0,0,1,0x68,2,0,0,0,1,0x65,3])
let nals = H264.nals(source)
precondition(nals == [Data([0x67,1]), Data([0x68,2]), Data([0x65,3])])
precondition(H264.avcc(nals) == Data([0,0,0,2,0x67,1,0,0,0,2,0x68,2,0,0,0,2,0x65,3]))
precondition(H264.nals(Data([1,2,3])).isEmpty)
precondition(H264.nals(Data([0,0,1])).isEmpty)
print("Annex B parsing and AVCC conversion passed")

func admittedFrame(_ result: VideoAdmission.Result) -> VideoAdmission.Frame {
    guard case .frame(let frame) = result else { fatalError("Expected admitted frame") }; return frame
}
func rejected(_ result: VideoAdmission.Result) -> Bool { if case .rejected = result { return true }; return false }
func header(_ result: VideoAdmission.Result) -> Bool { if case .header = result { return true }; return false }
let oldHeader = [Data([0x67, 1]), Data([0x68, 1])]
let newHeader = [Data([0x67, 2]), Data([0x68, 2])]
let idr = [Data([0x65, 3])], predictive = [Data([0x41, 4])]
let gate = VideoAdmission(capacity: 2)
precondition(header(gate.admit(oldHeader)))
let old1 = admittedFrame(gate.admit(idr)), old2 = admittedFrame(gate.admit(idr))
// Header is retained while the frame queue is saturated, without consuming capacity.
precondition(header(gate.admit(newHeader)))
precondition(rejected(gate.admit(idr)))
var displayed = 0
precondition(!gate.display(old1) { displayed += 1 })
precondition(!gate.canDisplay(old2))
gate.finish(old1); gate.finish(old2)
let current = admittedFrame(gate.admit(idr))
precondition(current.configuration.sps == newHeader[0] && current.configuration.pps == newHeader[1])
precondition(current.configuration.version > old1.configuration.version)
precondition(gate.display(current) { displayed += 1 }); gate.finish(current)
precondition(displayed == 1)
let next = admittedFrame(gate.admit(predictive)); gate.finish(next)
// A later drop must not be cleared by an older queued IDR of the same profile.
let olderIDR = admittedFrame(gate.admit(idr))
gate.drop(olderIDR)
precondition(gate.display(olderIDR) {}); gate.finish(olderIDR)
precondition(rejected(gate.admit(predictive)))
let recoveryIDR = admittedFrame(gate.admit(idr))
precondition(gate.display(recoveryIDR) {}); gate.finish(recoveryIDR)
let recovered = admittedFrame(gate.admit(predictive)); gate.finish(recovered)
// Reset invalidates old tickets while keeping their slots owned until finish.
let outstanding1 = admittedFrame(gate.admit(idr)), outstanding2 = admittedFrame(gate.admit(idr))
gate.reset(); precondition(header(gate.admit(newHeader)))
precondition(rejected(gate.admit(idr)))
precondition(!gate.display(outstanding1) {}); gate.finish(outstanding1); gate.finish(outstanding2)
let afterReset = admittedFrame(gate.admit(idr)); gate.finish(afterReset)
// Partial parameter sets never silently combine with a previous profile's other set.
let partialGate = VideoAdmission()
precondition(header(partialGate.admit([newHeader[0]])))
precondition(rejected(partialGate.admit(idr)))
precondition(header(partialGate.admit([newHeader[1]])))
let completedPair = admittedFrame(partialGate.admit(idr)); partialGate.finish(completedPair)
print("Saturated profile retention, versioned frame rejection, bounded reset and recovery-generation tests passed")

enum StartupFailure: Error { case unavailable }
let startup = StartupCache<AudioConfiguration, String>()
let audioKey = AudioConfiguration(channels: 2, rate: 48000)
let permits = DispatchSemaphore(value: 8)
var starts = 0, resets = 0
// More than eight failed attempts all reach startup; callers can release permits and retry.
for _ in 0..<10 {
    precondition(permits.wait(timeout: .now()) == .success)
    do {
        _ = try startup.ensure(audioKey, running: false, reset: { resets += 1 }, start: { starts += 1; throw StartupFailure.unavailable })
        fatalError("Expected startup failure")
    } catch { permits.signal() }
    precondition(startup.value == nil)
}
precondition(starts == 10 && resets == 20)
let started = try startup.ensure(audioKey, running: false, reset: { resets += 1 }, start: { starts += 1; return "format" })
precondition(started == "format" && starts == 11)
let reused = try startup.ensure(audioKey, running: true, reset: { fatalError("Unexpected reset") }, start: { fatalError("Unexpected cached startup") })
precondition(reused == "format")
// An externally stopped engine with the same format must restart.
_ = try startup.ensure(audioKey, running: false, reset: { resets += 1 }, start: { starts += 1; return "restarted" })
precondition(starts == 12 && startup.value == "restarted")
let changedKey = AudioConfiguration(channels: 1, rate: 24000)
do {
    _ = try startup.ensure(changedKey, running: true, reset: { resets += 1 }, start: { starts += 1; throw StartupFailure.unavailable })
    fatalError("Expected changed-format failure")
} catch { precondition(startup.value == nil) }
_ = try startup.ensure(changedKey, running: false, reset: { resets += 1 }, start: { starts += 1; return "new-format" })
precondition(starts == 14 && startup.value == "new-format")
print("Audio failed-start retry, uncached failure, running-engine reuse and stopped-engine restart tests passed")
