import SwiftUI

struct StreamView: View {
    @EnvironmentObject private var model: SessionModel
    @State private var chromeVisible = true
    // nil follows the controller: touch controls show only while no controller is connected.
    @State private var touchPreference: Bool?

    private var showsTouch: Bool { model.phase.isStreaming && (touchPreference ?? (model.controllerName == nil)) }

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            GeometryReader { proxy in
                if proxy.size.width > proxy.size.height {
                    ZStack { video; if showsTouch { TouchControls(input: model.input, topInset: Metrics.minimumTarget + Metrics.tight) } }
                } else {
                    VStack(spacing: 0) {
                        video
                        if showsTouch { TouchControls(input: model.input).frame(maxHeight: .infinity) } else { Spacer(minLength: 0) }
                    }
                }
            }
            VStack(spacing: 0) {
                if chromeVisible || !model.phase.isStreaming { chrome } else { revealButton }
                Spacer(minLength: 0)
            }
            stateCard
        }
        // The stream chrome sits on black video and always uses the dark palette.
        .environment(\.colorScheme, .dark)
        .streamChromeHidden(model.phase.isStreaming && !chromeVisible)
        .onAppear { Platform.keepAwake(true) }
        .onDisappear { Platform.keepAwake(false); model.input.releaseTouch() }
        .onChange(of: model.phase) { phase in
            if !phase.isStreaming { model.input.releaseTouch() }
            switch phase {
            // The menu stays up for people navigating with VoiceOver or Switch Control.
            case .streaming: Platform.announce("Connected"); chromeVisible = Platform.assistiveNavigationRunning
            case .loginRequired(_, let prompt): Platform.announce(prompt == .first ? "Console login PIN required" : "PIN not accepted. Enter it again."); chromeVisible = true
            case .ended(_, let end): Platform.announce(SessionCopy.message(for: end)); chromeVisible = true
            case .cleanupFailed: Platform.announce("Disconnect incomplete. Try again."); chromeVisible = true
            case .stopping: Platform.announce("Disconnecting"); chromeVisible = true
            default: chromeVisible = true
            }
        }
        .onChange(of: model.mediaIssue) { issue in if let issue { Platform.announce(issue) } }
        .onChange(of: showsTouch) { shown in if !shown { model.input.releaseTouch() } }
    }

    private var video: some View {
        StreamSurface(media: model.media).aspectRatio(16 / 9, contentMode: .fit)
            .frame(maxWidth: .infinity)
            .accessibilityLabel("Console video")
            .onTapGesture { if model.phase.isStreaming { chromeVisible.toggle() } }
    }

    private var stateText: String {
        switch model.phase {
        case .connecting: return "Connecting…"
        case .loginRequired: return "Console login PIN required"
        case .submittingLogin: return "Checking PIN…"
        case .streaming: return "Connected"
        case .stopping: return "Disconnecting…"
        case .ended: return "Session ended"
        case .cleanupFailed: return "Disconnect incomplete"
        default: return ""
        }
    }

    private var chrome: some View {
        StreamChrome(name: model.phase.streamConsole?.name ?? "", state: stateText, issue: model.mediaIssue,
                     streaming: model.phase.isStreaming, touchShown: showsTouch,
                     toggleTouch: { touchPreference = !showsTouch }, hide: { chromeVisible = false }, disconnect: { model.stop() })
    }

    private var revealButton: some View {
        HStack {
            Spacer()
            Button { chromeVisible = true } label: {
                // Dark backing keeps the control visible over bright video.
                Image(systemName: "ellipsis").font(.headline).foregroundColor(.white)
                    .frame(width: 36, height: 36).background(Circle().fill(Color.black.opacity(0.55)))
                    .frame(width: Metrics.minimumTarget, height: Metrics.minimumTarget).contentShape(Rectangle())
            }
            .accessibilityLabel("Show stream controls")
            .keyboardShortcut(.escape, modifiers: [])
        }
        .padding(.horizontal, Metrics.tight)
    }

    @ViewBuilder private var stateCard: some View {
        switch model.phase {
        case .connecting:
            StreamCard(title: "Connecting…", busy: true) {
                Button("Cancel") { model.stop() }.buttonStyle(GlassButtonStyle(kind: .secondary))
            }
        case .loginRequired(_, let prompt):
            LoginPINCard(prompt: prompt, submit: { model.submitLoginPIN($0) }, disconnect: { model.stop() })
        case .submittingLogin:
            StreamCard(title: "Checking PIN…", busy: true) {
                Button("Disconnect") { model.stop() }.buttonStyle(GlassButtonStyle(kind: .secondary))
            }
        case .stopping:
            StreamCard(title: "Disconnecting…", busy: true) { EmptyView() }
        case .ended(let console, let end):
            StreamCard(title: "Session ended", message: SessionCopy.message(for: end), detail: SessionCopy.detail(for: end)) {
                if end != .missingCredentials { Button("Retry") { model.connect(console) }.buttonStyle(GlassButtonStyle()) }
                Button("Back to consoles") { model.dismissSessionOutcome() }.buttonStyle(GlassButtonStyle(kind: .secondary))
            }
        case .cleanupFailed(_, let code):
            // The session is still owned natively; reconnecting or leaving now would be unsafe.
            StreamCard(title: "Disconnect incomplete", message: "GameRemote could not finish closing the session. Try again before starting another connection.", detail: "Core error \(code)") {
                Button("Try again") { model.stop() }.buttonStyle(GlassButtonStyle())
            }
        default: EmptyView()
        }
    }
}

private struct StreamChrome: View {
    @Environment(\.palette) private var palette
    let name: String, state: String, issue: String?
    let streaming: Bool, touchShown: Bool
    let toggleTouch: () -> Void, hide: () -> Void, disconnect: () -> Void
    var body: some View {
        VStack(alignment: .leading, spacing: Metrics.tight) {
            // Stacks when the row would truncate, for narrow widths and large text.
            ViewThatFits(in: .horizontal) {
                HStack(spacing: Metrics.related) { identity; Spacer(minLength: Metrics.related); actions }
                VStack(alignment: .leading, spacing: Metrics.related) { identity; actions }
            }
            if let issue { Label(issue, systemImage: "exclamationmark.triangle").font(.footnote).foregroundColor(palette.danger).fixedSize(horizontal: false, vertical: true) }
        }
        .padding(Metrics.related)
        .background(RoundedRectangle(cornerRadius: Metrics.panelRadius, style: .continuous).fill(palette.field))
        .overlay(RoundedRectangle(cornerRadius: Metrics.panelRadius, style: .continuous).strokeBorder(palette.edge, lineWidth: 1))
        .padding(.horizontal, Metrics.related).padding(.top, Metrics.tight)
        // Bounded so Disconnect stays on screen in landscape at the largest text sizes.
        .dynamicTypeSize(...DynamicTypeSize.accessibility2)
    }
    private var identity: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(name).font(.headline).foregroundColor(palette.text).fixedSize(horizontal: false, vertical: true)
            Text(state).font(.subheadline).foregroundColor(palette.muted)
        }
        .accessibilityElement(children: .combine)
    }
    private var actions: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: Metrics.tight) { actionButtons(fill: false) }
            VStack(spacing: Metrics.tight) { actionButtons(fill: true) }
        }
    }
    @ViewBuilder private func actionButtons(fill: Bool) -> some View {
        // Outside streaming, the state card owns Cancel/Disconnect; a second copy here would only confuse.
        if streaming {
            Button(touchShown ? "Hide touch controls" : "Show touch controls", action: toggleTouch).buttonStyle(GlassButtonStyle(kind: .secondary, fill: fill))
            Button("Hide menu", action: hide).buttonStyle(GlassButtonStyle(kind: .secondary, fill: fill))
            Button("Disconnect", action: disconnect).buttonStyle(GlassButtonStyle(kind: .danger, fill: fill))
        }
    }
}

// Opaque card over the video for connection states; never samples or blurs the frame behind it.
private struct StreamCard<Actions: View>: View {
    @Environment(\.palette) private var palette
    let title: String
    var message: String? = nil
    var detail: String? = nil
    var busy = false
    @ViewBuilder var actions: Actions
    @State private var showsDetail = false
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Metrics.standard) {
                HStack(spacing: Metrics.related) {
                    if busy { ProgressView() }
                    Text(title).font(.title3.bold()).foregroundColor(palette.text)
                }
                .accessibilityElement(children: .combine).accessibilityAddTraits(.isHeader)
                if let message { Text(message).font(.body).foregroundColor(palette.text).fixedSize(horizontal: false, vertical: true) }
                if let detail {
                    DisclosureGroup("Technical details", isExpanded: $showsDetail) {
                        Text(detail).font(.footnote).foregroundColor(palette.muted).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .font(.footnote).tint(palette.accent)
                }
                actions
            }
            .padding(Metrics.roomy)
            .background(RoundedRectangle(cornerRadius: Metrics.panelRadius, style: .continuous).fill(palette.field))
            .overlay(RoundedRectangle(cornerRadius: Metrics.panelRadius, style: .continuous).strokeBorder(palette.edge, lineWidth: 1))
            .frame(maxWidth: 420).padding(Metrics.roomy).frame(maxWidth: .infinity)
            .accessibilityAddTraits(.isModal)
        }
        .scrollBounceBehaviorIfAvailable()
    }
}

private struct LoginPINCard: View {
    @Environment(\.palette) private var palette
    let prompt: LoginPrompt
    let submit: (Data) -> Void, disconnect: () -> Void
    @State private var pin = ""
    @FocusState private var focused: Bool

    private var helper: String { "Enter your four-digit console login PIN." }
    private func send() {
        guard let data = RegistrationInput.loginPIN(pin) else { return }
        pin = ""; submit(data)
    }
    private var error: String? {
        switch prompt {
        case .first: return nil
        case .incorrect: return "That PIN was not accepted. Enter it again."
        case .submitFailed: return "The PIN could not be sent. Try again."
        }
    }

    var body: some View {
        StreamCard(title: "Console login PIN") {
            FieldChrome(label: "Console login PIN", helper: helper, error: error) {
                SecureField("Console login PIN", text: $pin, prompt: Text("")).digitInput().focused($focused).submitLabel(.go).onSubmit(send)
                    .toolbar { ToolbarItemGroup(placement: .keyboard) { Spacer(); Button("Done") { focused = false } } }
            }
            Button("Submit", action: send).buttonStyle(GlassButtonStyle()).disabled(RegistrationInput.loginPIN(pin) == nil)
            Button("Disconnect", action: disconnect).buttonStyle(GlassButtonStyle(kind: .danger))
        }
        // Focus is requested after the card is on screen; a request during presentation can be dropped.
        .onAppear { DispatchQueue.main.async { focused = true } }
        .onChange(of: prompt) { _ in pin = ""; focused = true }
    }
}

private extension View {
    // Centred when it fits, scrollable when large text or a keyboard needs the room.
    @ViewBuilder func scrollBounceBehaviorIfAvailable() -> some View {
        if #available(iOS 16.4, macOS 13.3, *) { scrollBounceBehavior(.basedOnSize) } else { self }
    }
}
