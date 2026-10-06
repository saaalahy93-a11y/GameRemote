import SwiftUI

struct ConsoleDraft: Hashable {
    var name = "", host = "", kind = ConsoleKind.ps5
    init() {}
    init(_ console: SavedConsole) { name = console.name; host = console.host; kind = console.kind }
}

enum Route: Hashable { case addConsole, register(ConsoleDraft), settings, help, licences }

struct RootView: View {
    @EnvironmentObject private var model: SessionModel
    @Environment(\.palette) private var palette
    @State private var path: [Route] = []

    var body: some View {
        NavigationStack(path: $path) {
            HomeView(path: $path)
                .navigationDestination(for: Route.self) { route in
                    switch route {
                    case .addConsole: AddConsoleView(path: $path)
                    case .register(let draft): RegisterView(path: $path, draft: draft)
                    case .settings: SettingsView(path: $path)
                    case .help: HelpView()
                    case .licences: LicencesView()
                    }
                }
        }
        .tint(palette.accent)
        .onChange(of: path) { path in
            let inRegistration = path.contains { if case .register = $0 { return true }; return false }
            if !inRegistration { model.dismissRegistrationOutcome() }
        }
        // Presentation follows the model; the stream is dismissed only by an actual lifecycle outcome.
        .streamCover(isPresented: Binding(get: { model.phase.streamConsole != nil }, set: { _ in })) {
            StreamView().environmentObject(model)
        }
        .alert("Saved consoles", isPresented: Binding(get: { model.libraryIssue != nil }, set: { if !$0 { model.libraryIssue = nil } }), presenting: model.libraryIssue) { issue in
            if issue == .loadFailed { Button("Reset saved consoles", role: .destructive) { model.resetLibrary() } }
            Button(issue == .loadFailed ? "Not now" : "OK", role: .cancel) {}
        } message: { issue in Text(issue.message) }
    }
}

struct HomeView: View {
    @EnvironmentObject private var model: SessionModel
    @Environment(\.palette) private var palette
    @Environment(\.dynamicTypeSize) private var typeSize
    @Binding var path: [Route]
    @State private var selectedID: UUID?

    private var selected: SavedConsole? { model.consoles.first { $0.id == selectedID } ?? model.consoles.first }

    var body: some View {
        GeometryReader { proxy in
            // Support sits beside the stage only when both remain readable; otherwise one reading order.
            let wide = proxy.size.width >= 900 && !typeSize.isAccessibilitySize
            let margin: CGFloat = proxy.size.width >= 700 ? Metrics.section : proxy.size.width < 360 || typeSize.isAccessibilitySize ? Metrics.standard : Metrics.roomy
            ScrollView {
                VStack(alignment: .leading, spacing: Metrics.roomy) {
                    if let issue = model.mediaIssue {
                        NoticePanel(title: "Media output", message: issue, detail: nil)
                    }
                    if wide {
                        HStack(alignment: .top, spacing: Metrics.roomy) {
                            stage(artworkHeight: 132).frame(width: (proxy.size.width - margin * 2 - Metrics.roomy) * 2 / 3)
                            SupportPanel(path: $path)
                        }
                    } else {
                        stage(artworkHeight: 88)
                        SupportPanel(path: $path)
                    }
                    otherConsoles
                }
                .padding(.horizontal, margin).padding(.vertical, Metrics.roomy)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .background(GlassBackdrop())
        // A newly registered console takes the stage.
        .onChange(of: model.phase) { phase in if case .registered(let console) = phase { selectedID = console.id } }
        .navigationTitle("Consoles").inlineNavigationTitle()
        .toolbar {
            ToolbarItem(placement: .principal) { BrandLockup() }
            ToolbarItemGroup(placement: .primaryAction) {
                Button { path.append(.addConsole) } label: { Label("Add console", systemImage: "plus") }
                    .accessibilityIdentifier("home.add-console")
                Button { path.append(.settings) } label: { Label("Settings", systemImage: "gearshape") }
                    .accessibilityIdentifier("home.settings")
            }
        }
    }

    @ViewBuilder private func stage(artworkHeight: CGFloat) -> some View {
        if let console = selected {
            let registered = model.registeredIDs.contains(console.id)
            VStack(alignment: .leading, spacing: Metrics.standard) {
                ConsoleSilhouette(kind: console.kind).frame(maxWidth: .infinity).frame(height: artworkHeight).accessibilityHidden(true)
                HStack(alignment: .top, spacing: Metrics.related) {
                    ConsoleSummary(console: console, registered: registered, prominent: true)
                    Spacer(minLength: 0)
                    ConsoleOptionsMenu(console: console)
                }
                Button(registered ? "Connect" : "Set up") {
                    if registered { model.connect(console) } else { path.append(.register(ConsoleDraft(console))) }
                }
                .buttonStyle(GlassButtonStyle()).disabled(!model.phase.allowsNewOperation)
            }
            .padding(Metrics.standard).glassPanel(.stage)
        } else {
            SetupGuide(path: $path)
        }
    }

    @ViewBuilder private var otherConsoles: some View {
        let others = model.consoles.filter { $0.id != selected?.id }
        if !others.isEmpty {
            VStack(alignment: .leading, spacing: Metrics.related) {
                Text("Other consoles").font(.headline).foregroundColor(palette.text).accessibilityAddTraits(.isHeader)
                ForEach(others) { console in
                    // Selecting only changes the stage; connecting stays an explicit action there.
                    Button { selectedID = console.id; Platform.announce("Showing \(console.name) on the stage") } label: {
                        HStack(spacing: Metrics.related) {
                            ConsoleSummary(console: console, registered: model.registeredIDs.contains(console.id), prominent: false)
                            Spacer(minLength: 0)
                            Image(systemName: "arrow.up.left.circle").font(.title3).foregroundColor(palette.accent).accessibilityHidden(true)
                        }
                        .padding(Metrics.standard).frame(maxWidth: .infinity, minHeight: Metrics.minimumTarget, alignment: .leading)
                        .glassPanel(.support).contentShape(Rectangle())
                    }
                    .buttonStyle(.plain).accessibilityHint("Shows this console on the stage")
                }
            }
        }
    }
}

struct ConsoleSummary: View {
    @Environment(\.palette) private var palette
    let console: SavedConsole, registered: Bool, prominent: Bool
    var body: some View {
        VStack(alignment: .leading, spacing: Metrics.detail) {
            Text(console.name).font(prominent ? .title2.bold() : .headline).foregroundColor(palette.text)
            Text(console.kind.title).font(.body).foregroundColor(palette.muted)
            // Registration is what this device knows; it is not a claim that the console is reachable.
            StatusLabel(text: registered ? "Registered on this device" : "Registration required", tone: registered ? .success : .neutral)
            Text(console.host).font(.footnote).foregroundColor(palette.muted)
        }
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .combine)
    }
}

// Rename and remove share one confirmation path wherever a console is listed.
struct ConsoleOptionsMenu: View {
    @EnvironmentObject private var model: SessionModel
    @Environment(\.palette) private var palette
    let console: SavedConsole
    @State private var renaming = false
    @State private var removing = false
    @State private var name = ""
    var body: some View {
        Menu {
            Button { name = console.name; renaming = true } label: { Label("Rename", systemImage: "pencil") }
            Button(role: .destructive) { removing = true } label: { Label("Remove", systemImage: "trash") }
        } label: {
            Image(systemName: "ellipsis.circle").font(.title3).foregroundColor(palette.accent)
                .frame(minWidth: Metrics.minimumTarget, minHeight: Metrics.minimumTarget).contentShape(Rectangle())
        }
        .accessibilityLabel("Options for \(console.name)")
        .alert("Rename console", isPresented: $renaming) {
            TextField("Name", text: $name)
            Button("Save") { model.rename(console, to: name) }
            Button("Cancel", role: .cancel) {}
        }
        .confirmationDialog("Remove “\(console.name)”?", isPresented: $removing, titleVisibility: .visible) {
            Button("Remove console", role: .destructive) { model.remove(console) }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Its saved credentials are deleted from this device. Playing again needs a new pairing code from the console.")
        }
    }
}

struct SupportPanel: View {
    @EnvironmentObject private var model: SessionModel
    @Environment(\.palette) private var palette
    @Binding var path: [Route]
    var body: some View {
        VStack(alignment: .leading, spacing: Metrics.related) {
            Text("Connection").font(.headline).foregroundColor(palette.text).accessibilityAddTraits(.isHeader)
            DetailRow(title: "Stream profile", value: SessionCopy.profile)
            DetailRow(title: "Network", value: "Local network only")
            DetailRow(title: "Controller", value: model.controllerName.map { "Controller connected: \($0)" } ?? "No controller connected. Touch controls appear while playing.")
            Button("Setup help") { path.append(.help) }.buttonStyle(GlassButtonStyle(kind: .secondary))
        }
        .padding(Metrics.standard).frame(maxWidth: .infinity, alignment: .leading).glassPanel(.support)
    }
}

struct DetailRow: View {
    @Environment(\.palette) private var palette
    let title: String, value: String
    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title).font(.footnote).foregroundColor(palette.muted)
            Text(value).font(.body).foregroundColor(palette.text).fixedSize(horizontal: false, vertical: true)
        }
        .accessibilityElement(children: .combine)
    }
}

struct SetupGuide: View {
    @Environment(\.palette) private var palette
    @Binding var path: [Route]
    static let steps = [
        "On your console, turn on Remote Play.",
        "Keep this device and the console on the same local network.",
        "Open Link Device on the console to show an eight-digit pairing code.",
        "Have your PSN account ID ready in base64 form. This app cannot look it up."]
    var body: some View {
        VStack(alignment: .leading, spacing: Metrics.standard) {
            Text("Set up Remote Play").font(.title2.bold()).foregroundColor(palette.text).accessibilityAddTraits(.isHeader)
            Text("Add your console by its address, then register it with a pairing code.").font(.body).foregroundColor(palette.muted)
            VStack(alignment: .leading, spacing: Metrics.related) {
                ForEach(Array(Self.steps.enumerated()), id: \.offset) { index, step in
                    HStack(alignment: .firstTextBaseline, spacing: Metrics.related) {
                        Text("\(index + 1).").font(.body.weight(.semibold)).foregroundColor(palette.accent)
                        Text(step).font(.body).foregroundColor(palette.text).fixedSize(horizontal: false, vertical: true)
                    }
                    .accessibilityElement(children: .combine)
                }
            }
            Button("Connect manually") { path.append(.addConsole) }.buttonStyle(GlassButtonStyle())
            Button("Controller help") { path.append(.help) }.buttonStyle(GlassButtonStyle(kind: .secondary))
        }
        .padding(Metrics.standard).frame(maxWidth: .infinity, alignment: .leading).glassPanel(.stage)
    }
}
