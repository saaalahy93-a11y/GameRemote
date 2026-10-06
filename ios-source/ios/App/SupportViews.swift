import SwiftUI

struct SectionPanel<Content: View>: View {
    @Environment(\.palette) private var palette
    let title: String
    @ViewBuilder var content: Content
    var body: some View {
        VStack(alignment: .leading, spacing: Metrics.related) {
            Text(title).font(.headline).foregroundColor(palette.text).accessibilityAddTraits(.isHeader)
            content
        }
        .padding(Metrics.standard).frame(maxWidth: .infinity, alignment: .leading).glassPanel(.support)
    }
}

struct BodyText: View {
    @Environment(\.palette) private var palette
    let text: String
    init(_ text: String) { self.text = text }
    var body: some View { Text(text).font(.body).foregroundColor(palette.text).fixedSize(horizontal: false, vertical: true) }
}

struct SettingsView: View {
    @EnvironmentObject private var model: SessionModel
    @Environment(\.palette) private var palette
    @Binding var path: [Route]

    private var version: String {
        let info = Bundle.main.infoDictionary
        return "\(info?["CFBundleShortVersionString"] as? String ?? "–") (\(info?["CFBundleVersion"] as? String ?? "–"))"
    }

    var body: some View {
        FormPage(title: "Settings") {
            // Read-only: the engine has one profile in this version.
            SectionPanel(title: "Stream profile") {
                DetailRow(title: "Resolution", value: "720p")
                DetailRow(title: "Frame rate", value: "60 fps target")
                DetailRow(title: "Video", value: "H.264")
                Text("These values are fixed in this version.").font(.footnote).foregroundColor(palette.muted)
            }
            SectionPanel(title: "Controller") {
                DetailRow(title: "Status", value: model.controllerName.map { "Controller connected: \($0)" } ?? "No controller connected")
                BodyText("A paired game controller is used automatically. Touch controls appear on screen while playing when no controller is connected, and can be switched on or off from the stream menu.")
                BodyText("Not supported in this version: touchpad swipes, motion sensors, rumble, adaptive triggers and the microphone.")
            }
            SectionPanel(title: "Local network") {
                BodyText("GameRemote connects only to the console address you enter, on your local network. If registration or connection fails, check that Local Network access is allowed for GameRemote.")
                Button("Open app settings") { Platform.openAppSettings() }.buttonStyle(GlassButtonStyle(kind: .secondary))
            }
            SectionPanel(title: "Saved consoles") {
                if model.consoles.isEmpty { BodyText("No consoles are saved on this device.") }
                ForEach(model.consoles) { console in
                    HStack(alignment: .top, spacing: Metrics.related) {
                        ConsoleSummary(console: console, registered: model.registeredIDs.contains(console.id), prominent: false)
                        Spacer(minLength: 0)
                        ConsoleOptionsMenu(console: console)
                    }
                }
                Button("Add console") { path.append(.addConsole) }.buttonStyle(GlassButtonStyle(kind: .secondary))
            }
            SectionPanel(title: "Privacy") {
                BodyText("GameRemote does not collect, upload or share data. Console names and addresses are stored on this device. Pairing credentials are stored in this device's Keychain and are not synced or transferred to other devices.")
                if let url = AppLinks.current.privacyPolicy {
                    Link("Privacy policy", destination: url).buttonStyle(GlassButtonStyle(kind: .secondary))
                        .accessibilityIdentifier("settings.privacyPolicy")
                } else {
                    BodyText("A public privacy policy link has not been configured for this development build.")
                }
            }
            SectionPanel(title: "About") {
                DetailRow(title: "Version", value: version)
                BodyText("GameRemote is an unofficial Remote Play client. It is not endorsed or certified by Sony Interactive Entertainment LLC.")
                Button("Setup help") { path.append(.help) }.buttonStyle(GlassButtonStyle(kind: .secondary))
                    .accessibilityIdentifier("settings.help")
                Button("Licences and credits") { path.append(.licences) }.buttonStyle(GlassButtonStyle(kind: .secondary))
                    .accessibilityIdentifier("settings.licences")
            }
        }
    }
}

struct HelpView: View {
    var body: some View {
        FormPage(title: "Setup help") {
            SectionPanel(title: "Before you start") {
                BodyText("Your console and this device must be on the same local network. Searching for consoles, waking a console and playing over the internet are not available in this version.")
            }
            SectionPanel(title: "Turn on Remote Play") {
                BodyText("PlayStation 5: Settings, System, Remote Play, then turn on Enable Remote Play.")
                BodyText("PlayStation 4: Settings, Remote Play Connection Settings, then turn on Enable Remote Play.")
            }
            SectionPanel(title: "Console address") {
                BodyText("Find the console's IP address in its network settings under View Connection Status, and enter it when you add the console.")
            }
            SectionPanel(title: "PSN account ID") {
                BodyText("Registration needs the account ID of the console account in base64 form. It decodes to eight bytes and is not your sign-in ID or password. This app cannot sign in to PlayStation Network or look the ID up; obtain it with GameRemote on another platform or another tool, then paste it here.")
                BodyText("GameRemote never asks for your PSN password.")
            }
            SectionPanel(title: "Pairing code") {
                BodyText("PlayStation 5: Settings, System, Remote Play, Link Device. PlayStation 4: Settings, Remote Play Connection Settings, Add Device. The console shows an eight-digit code for a few minutes. A code works once; a failed attempt needs a new code.")
            }
            SectionPanel(title: "Console login PIN") {
                BodyText("If the console account is protected by a four-digit login PIN, GameRemote asks for it while connecting. It is separate from the pairing code and is not saved.")
            }
            SectionPanel(title: "Controllers") {
                BodyText("Pair a controller in Bluetooth settings on this device before connecting. Sticks, buttons, triggers, the PS button and the touchpad click are sent to the console. The system may reserve the PS or Home button for its own use.")
                BodyText("Without a controller, on-screen touch controls are shown while playing.")
            }
            SectionPanel(title: "Support") {
                if let url = AppLinks.current.support {
                    Link("Contact support", destination: url).buttonStyle(GlassButtonStyle(kind: .secondary))
                        .accessibilityIdentifier("help.support")
                } else {
                    BodyText("A public support link has not been configured for this development build.")
                }
            }
        }
    }
}

struct LicencesView: View {
    @Environment(\.palette) private var palette
    @State private var documents: [(title: String, paragraphs: [String])] = []

    private static let sources = [("GameRemote licence (AGPL-3.0-only with OpenSSL permission)", "AGPL-3.0-only-OpenSSL"), ("Third-party notices", "ThirdPartyNotices")]

    var body: some View {
        FormPage(title: "Licences and credits") {
            SectionPanel(title: "Credits") {
                BodyText("GameRemote is a derivative of chiaki-ng, which builds on the original Chiaki project. Their authors' copyright, attribution and licence notices are preserved.")
                BodyText("The source code is licensed under the GNU Affero General Public License version 3 only, with the existing OpenSSL additional permission. You are entitled to the corresponding source for this build.")
                if let url = AppLinks.current.source {
                    Link("Source code for this build", destination: url).buttonStyle(GlassButtonStyle(kind: .secondary))
                        .accessibilityIdentifier("licences.source")
                } else {
                    BodyText("A public corresponding-source link has not been configured for this development build.")
                }
            }
            ForEach(documents, id: \.title) { document in
                SectionPanel(title: document.title) {
                    // Paragraph-sized pieces keep long licence text cheap to lay out.
                    LazyVStack(alignment: .leading, spacing: Metrics.tight) {
                        ForEach(Array(document.paragraphs.enumerated()), id: \.offset) { _, paragraph in
                            Text(paragraph).font(.footnote).foregroundColor(palette.text).fixedSize(horizontal: false, vertical: true).textSelection(.enabled)
                        }
                    }
                }
            }
        }
        .onAppear { if documents.isEmpty { documents = Self.sources.map { ($0.0, Self.paragraphs(named: $0.1)) } } }
    }

    private static func paragraphs(named name: String) -> [String] {
        guard let url = Bundle.main.url(forResource: name, withExtension: "txt"), let text = try? String(contentsOf: url, encoding: .utf8) else {
            return ["This text is missing from the app bundle. It is available with the source code."]
        }
        return text.components(separatedBy: "\n\n").map { $0.trimmingCharacters(in: .newlines) }.filter { !$0.isEmpty }
    }
}
