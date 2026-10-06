import Foundation
import SwiftUI

func check(_ condition: @autoclosure () -> Bool, _ message: String, line: UInt = #line) {
    if !condition() { fatalError("\(message) (line \(line))") }
}
func failure<T>(_ body: () throws -> T) -> ConsoleIndex.Failure? {
    do { _ = try body(); return nil } catch { return error as? ConsoleIndex.Failure }
}

// MARK: Field validation
check(RegistrationInput.host("  192.168.1.20\n") == "192.168.1.20", "host is trimmed")
check(RegistrationInput.host("PS5.local") == "PS5.local", "host case is preserved for the Keychain key")
check(RegistrationInput.host("   ") == nil && RegistrationInput.host("ps 5") == nil, "empty and spaced hosts are rejected")
check(RegistrationInput.host(String(repeating: "a", count: 256)) == nil && RegistrationInput.host(String(repeating: "a", count: 255)) != nil, "host limit matches the bridge")
for bad in ["ps5\u{0}.evil", "ps5\u{7}", "ps5\u{200B}local", "ps5\u{A0}local"] { check(RegistrationInput.host(bad) == nil, "host with control, format or non-breaking space characters is rejected") }
check(RegistrationInput.account("AQIDBAUGBwg=") == Data([1, 2, 3, 4, 5, 6, 7, 8]), "eight-byte base64 account decodes")
check(RegistrationInput.account(" AQIDBAUGBwg= ") != nil, "pasted account padding whitespace is tolerated")
check(RegistrationInput.account("AQIDBAUGBw==") == nil && RegistrationInput.account("AQIDBAUGBwgJ") == nil, "seven and nine byte accounts are rejected")
check(RegistrationInput.account("not base64!") == nil && RegistrationInput.account("") == nil, "invalid base64 is rejected")
check(RegistrationInput.pairingCode("01234567") == 1234567, "leading zero pairing code is accepted")
for bad in ["1234567", "123456789", "1234567a", "+1234567", " 1234567", "١٢٣٤٥٦٧٨", ""] { check(RegistrationInput.pairingCode(bad) == nil, "pairing code \(bad) is rejected") }
check(RegistrationInput.loginPIN("0042") == Data("0042".utf8), "login PIN keeps leading zeroes as digits")
for bad in ["123", "12345", "12a4", "١٢٣٤", ""] { check(RegistrationInput.loginPIN(bad) == nil, "login PIN \(bad) is rejected") }
check(RegistrationInput.name("  ", host: "10.0.0.2") == "10.0.0.2" && RegistrationInput.name(" Den ", host: "h") == "Den", "name falls back to the address")
print("Registration field validation passed")

// MARK: Saved-console index
let directory = FileManager.default.temporaryDirectory.appendingPathComponent("gameremote-index-\(UUID().uuidString)")
defer { try? FileManager.default.removeItem(at: directory) }
let file = directory.appendingPathComponent("nested/consoles.json")
let index = ConsoleIndex(url: file)
check(try! index.load().isEmpty, "a missing file is an empty list")
let first = try! index.save(name: "Den", host: "192.168.1.20", kind: .ps5)
let second = try! index.save(name: "Office", host: "PS4.local", kind: .ps4)
check(second.all.count == 2 && first.console.id != second.console.id, "two hosts are two consoles")
check(try! ConsoleIndex(url: file).load() == second.all, "the list persists across instances")
let updated = try! index.save(name: "Den PS5", host: "192.168.1.20", kind: .ps4)
check(updated.console.id == first.console.id && updated.all.count == 2 && updated.console.kind == .ps4, "re-registering a host keeps its identity")
check(try! index.save(name: "Other", host: "ps4.local", kind: .ps4).all.count == 3, "hosts are matched exactly, never normalized")
check(try! index.save(name: "Composed", host: "caf\u{E9}.local", kind: .ps5).all.count == 4 && (try! index.save(name: "Decomposed", host: "cafe\u{301}.local", kind: .ps5).all.count) == 5, "Unicode-equivalent hosts stay separate, as in the Keychain")
check(try! index.rename(id: first.console.id, name: "Lounge").first { $0.id == first.console.id }?.name == "Lounge", "rename persists")
check(try! index.rename(id: UUID(), name: "Ghost").count == 5, "renaming an unknown console changes nothing")
check(try! index.remove(id: second.console.id).contains { $0.id == second.console.id } == false, "remove deletes the entry")
let stored = try! JSONSerialization.jsonObject(with: Data(contentsOf: file)) as! [String: Any]
let keys = Set((stored["consoles"] as! [[String: Any]]).flatMap { $0.keys })
check(keys == ["id", "name", "host", "kind"] && Set(stored.keys) == ["version", "consoles"], "only non-secret metadata is written")

let corrupt = Data("{ not json".utf8)
try! corrupt.write(to: file)
check(failure { try index.load() } == .unreadable, "a corrupt file is reported")
check(failure { try index.save(name: "X", host: "x", kind: .ps5) } == .unreadable && failure { try index.remove(id: UUID()) } == .unreadable, "a corrupt file blocks writes")
check(try! Data(contentsOf: file) == corrupt, "a corrupt file is never silently replaced")
try! Data(#"{"version":99,"consoles":[]}"#.utf8).write(to: file)
check(failure { try index.load() } == .unreadable, "a newer file version is not misread")
try! Data(#"{"version":1,"consoles":[{"id":"6F9619FF-8B86-D011-B42D-00C04FC964FF","name":"x","host":"ps5\u0000.evil","kind":"ps5"}]}"#.utf8).write(to: file)
check(failure { try index.load() } == .unreadable, "a list entry with an unsafe host is not loaded")
try! index.reset()
check(try! index.load().isEmpty, "explicit reset recovers an unreadable list")
let blocked = directory.appendingPathComponent("blocker")
try! Data().write(to: blocked)
check(failure { try ConsoleIndex(url: blocked.appendingPathComponent("consoles.json")).save(name: "X", host: "x", kind: .ps5) } == .unwritable, "an unwritable location is reported")
print("Saved-console index persistence, exact-host identity, corruption and write-failure tests passed")

// MARK: Input aggregation
let input = InputAggregator()
input.setButton(.cross, pressed: true); input.setButton(.l1, pressed: true)
// The regression this guards: a poll carrying idle physical state must not clear a held touch.
for _ in 0..<5 { check(input.merged(with: PadState()).buttons == PadButton.cross.rawValue | PadButton.l1.rawValue, "held touch survives every poll") }
var physical = PadState(); physical.buttons = PadButton.circle.rawValue; physical.l2 = 90; physical.lx = 20000; physical.ry = -100
input.setTrigger(left: true, pressed: true); input.setTrigger(left: false, pressed: true); input.setTrigger(left: false, pressed: false)
input.setStick(left: true, x: 0.1, y: 0); input.setStick(left: false, x: 3, y: 4)
let merged = input.merged(with: physical)
check(merged.buttons == PadButton.cross.rawValue | PadButton.l1.rawValue | PadButton.circle.rawValue, "touch and physical buttons combine")
check(merged.l2 == 255 && merged.r2 == 0, "triggers take the stronger source and release cleanly")
check(merged.lx == 20000 && merged.ly == 0, "the further-deflected physical stick wins")
check(merged.rx == PadState.axis(0.6) && merged.ry == PadState.axis(0.8), "touch stick is clamped to the unit circle")
input.setButton(.cross, pressed: false)
check(input.merged(with: PadState()).buttons == PadButton.l1.rawValue, "releasing one control leaves the others held")
input.releaseTouch()
check(input.merged(with: PadState()) == PadState() && input.merged(with: physical) == physical, "release clears every touch contribution")
check(PadState.axis(2) == 32767 && PadState.axis(-2) == -32767 && PadState.axis(0) == 0, "axis conversion clamps")
check(Set(PadButton.allCases.map(\.rawValue)).count == 16 && PadButton.allCases.reduce(0) { $0 | $1.rawValue } == 0xFFFF, "button bits are distinct and cover the core mask")
check(PadGeometry.directions(dx: 0, dy: 0, deadZone: 12) == 0 && PadGeometry.directions(dx: 5, dy: -8, deadZone: 12) == 0, "dead zone holds nothing")
check(PadGeometry.directions(dx: 0, dy: -40, deadZone: 12) == PadButton.dpadUp.rawValue, "up")
check(PadGeometry.directions(dx: 40, dy: 5, deadZone: 12) == PadButton.dpadRight.rawValue, "right with slight drift")
check(PadGeometry.directions(dx: -30, dy: 30, deadZone: 12) == PadButton.dpadLeft.rawValue | PadButton.dpadDown.rawValue, "diagonal holds two directions")
print("Input merge, hold-across-polls, release and direction-pad geometry tests passed")

// MARK: Touch control fit
// These are usable safe-area sizes, including the smallest landscape phone and narrower
// notched-phone safe areas. The 52pt inset reserves the stream menu above the controls.
for size in [CGSize(width: 480, height: 320), CGSize(width: 568, height: 320),
             CGSize(width: 659, height: 354), CGSize(width: 750, height: 369),
             CGSize(width: 844, height: 369), CGSize(width: 932, height: 409),
             CGSize(width: 1024, height: 724), CGSize(width: 1194, height: 790)] {
    let layout = TouchControlLayout(size: size, topInset: 52)
    check(layout.style != .stacked, "landscape uses a single gamepad band at \(size)")
    check(layout.minimumSize.width <= size.width && layout.minimumSize.height + 52 <= size.height,
          "every control fits inside the usable landscape bounds at \(size)")
    check(layout.faceDiameter >= 44 && layout.stickDiameter >= 44 && TouchControlLayout.target >= 44,
          "compact controls retain 44pt hit targets")
}
let expanded = TouchControlLayout(size: CGSize(width: 672, height: 300), topInset: 52)
check(expanded.style == .expanded && expanded.minimumSize == CGSize(width: 672, height: 248), "expanded row fits exactly at its measured width and height")
check(TouchControlLayout(size: CGSize(width: 671, height: 300), topInset: 52).style == .compact, "one point below the wide-row width uses compact controls")
check(TouchControlLayout(size: CGSize(width: 672, height: 299), topInset: 52).style == .compact, "available height also governs the row choice")
let compact = TouchControlLayout(size: CGSize(width: 472, height: 268), topInset: 52)
check(compact.style == .compact && compact.minimumSize == CGSize(width: 472, height: 216), "compact row includes every gap and the menu reservation")
let portrait = TouchControlLayout(size: CGSize(width: 320, height: 440), topInset: 0)
check(portrait.style == .stacked && portrait.minimumSize.width <= 320 && portrait.minimumSize.height <= 440, "narrow portrait keeps reachable sticks")
print("Touch controls fit phone/iPad safe areas, menu inset and width/height boundaries; 44pt targets retained")

// MARK: Typed phases
let console = first.console
let sessionPhases: [SessionPhase] = [.connecting(console), .loginRequired(console, .first), .submittingLogin(console), .streaming(console), .stopping(console), .ended(console, .quit(reason: 4)), .cleanupFailed(console, code: 1)]
check(sessionPhases.allSatisfy { $0.streamConsole == console }, "every session phase keeps the stream presented")
let setupPhases: [SessionPhase] = [.idle, .registering(host: "h"), .registered(console), .registrationFailed(.rejected), .stopping(nil)]
check(setupPhases.allSatisfy { $0.streamConsole == nil }, "registration phases never present the stream")
check([SessionPhase.idle, .registered(console), .registrationFailed(.rejected), .ended(console, .missingCredentials)].allSatisfy { $0.allowsNewOperation }, "settled phases allow a new operation")
check([SessionPhase.registering(host: "h"), .connecting(console), .streaming(console), .stopping(console), .cleanupFailed(console, code: 1), .loginRequired(console, .incorrect)].allSatisfy { !$0.allowsNewOperation }, "busy and retained-cleanup phases block a new operation")
for reason in Int32(0)...14 { check(!SessionCopy.message(for: .quit(reason: reason)).isEmpty && SessionCopy.detail(for: .quit(reason: reason)) == "Quit reason \(reason)", "quit reason \(reason) has user text and keeps its code") }
check(SessionCopy.detail(for: SessionEnd.startFailed(code: 9)) == "Core error 9" && SessionCopy.detail(for: SessionEnd.missingCredentials) == nil, "start failures keep diagnostics")
print("Typed phase presentation and recovery-copy tests passed")

// MARK: Console artwork paths
let box = SVGPath.parse("M 0,0 H 10 V 5 h -10 z").boundingRect
check(box == CGRect(x: 0, y: 0, width: 10, height: 5), "absolute and relative line commands")
check(SVGPath.parse("m 1,1 2,0 0,2 z").boundingRect == CGRect(x: 1, y: 1, width: 2, height: 2), "implicit relative line-tos")
check(SVGPath.parse("M 0,0 c 0,10 10,10 10,0").boundingRect.width == 10, "relative curve")
check(SVGPath.parse("M 5,-1.8e-4 L 6,1").boundingRect.minY < 0, "exponent numbers")
for art in [ConsoleSilhouette.ps5, ConsoleSilhouette.ps4] {
    let bounds = art.path.boundingRect
    check(!art.path.isEmpty && bounds.minX >= -0.5 && bounds.minY >= -0.5 && bounds.maxX <= art.size.width + 0.5 && bounds.maxY <= art.size.height + 0.5, "silhouette stays inside its view box")
    check(bounds.width > art.size.width * 0.9, "silhouette spans its view box")
}
print("Console artwork path parsing tests passed")
