import SwiftUI

@main struct GameRemoteApp: App {
    @StateObject private var model = SessionModel()
    @Environment(\.scenePhase) private var scenePhase
    var body: some Scene {
        WindowGroup {
            RootView().environmentObject(model)
                .onChange(of: scenePhase) { phase in
                    // Any interruption releases held touch input. The session itself stops in the background only,
                    // so a system prompt such as the local-network permission alert does not cancel pairing.
                    if phase != .active { model.input.releaseTouch() }
                    if phase == .background { model.stop(then: Platform.backgroundWindow()) }
                    if phase == .active { model.reloadLibrary() }
                }
        }
    }
}
