import SwiftUI
import UIKit

// Every UIKit-only call lives in this file; ios/tests/PlatformHostStub.swift mirrors it for host typechecking.
struct StreamSurface: UIViewRepresentable {
    let media: Media
    func makeUIView(context: Context) -> VideoView { media.view }
    func updateUIView(_ uiView: VideoView, context: Context) {}
}

extension View {
    func addressInput() -> some View { textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.numbersAndPunctuation) }
    func identifierInput() -> some View { textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.asciiCapable) }
    // One-time-code content type keeps the Passwords autofill bar off these short-lived codes.
    func digitInput() -> some View { keyboardType(.numberPad).textContentType(.oneTimeCode) }
    func inlineNavigationTitle() -> some View { navigationBarTitleDisplayMode(.inline) }
    func streamCover<Content: View>(isPresented: Binding<Bool>, @ViewBuilder content: @escaping () -> Content) -> some View {
        fullScreenCover(isPresented: isPresented, content: content)
    }
    func streamChromeHidden(_ hidden: Bool) -> some View { statusBarHidden(hidden).persistentSystemOverlays(hidden ? .hidden : .automatic) }
}

enum Platform {
    // Queued, so one outcome does not cut off another or the element being read.
    static func announce(_ message: String) {
        UIAccessibility.post(notification: .announcement, argument: NSAttributedString(string: message, attributes: [.accessibilitySpeechQueueAnnouncement: true]))
    }
    static var assistiveNavigationRunning: Bool { UIAccessibility.isVoiceOverRunning || UIAccessibility.isSwitchControlRunning }
    // A controller-only session produces no touches, so the display would otherwise sleep mid-game.
    static func keepAwake(_ enabled: Bool) { UIApplication.shared.isIdleTimerDisabled = enabled }
    // Keeps the process alive while a background-triggered stop joins the session thread.
    static func backgroundWindow() -> () -> Void {
        var task = UIBackgroundTaskIdentifier.invalid
        let end = { if task != .invalid { UIApplication.shared.endBackgroundTask(task); task = .invalid } }
        task = UIApplication.shared.beginBackgroundTask(withName: "Stop session", expirationHandler: end)
        return end
    }
    static func openAppSettings() {
        if let url = URL(string: UIApplication.openSettingsURLString) { UIApplication.shared.open(url) }
    }
}
