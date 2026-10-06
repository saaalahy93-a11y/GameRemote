// Compile-only macOS mirror of ios/App/Platform.swift so the remaining SwiftUI sources can be
// typechecked without an iOS SDK. Excluded from the app target; not evidence of iOS behaviour.
import SwiftUI

struct StreamSurface: View {
    let media: Media
    var body: some View { Color.black }
}

extension View {
    func addressInput() -> some View { self }
    func identifierInput() -> some View { self }
    func digitInput() -> some View { self }
    func inlineNavigationTitle() -> some View { self }
    func streamCover<Content: View>(isPresented: Binding<Bool>, @ViewBuilder content: @escaping () -> Content) -> some View {
        sheet(isPresented: isPresented, content: content)
    }
    func streamChromeHidden(_ hidden: Bool) -> some View { self }
}

enum Platform {
    static func announce(_ message: String) {}
    static var assistiveNavigationRunning: Bool { false }
    static func keepAwake(_ enabled: Bool) {}
    static func backgroundWindow() -> () -> Void { {} }
    static func openAppSettings() {}
}
