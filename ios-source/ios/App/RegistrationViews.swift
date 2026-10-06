import SwiftUI

// Single-column form page used by setup, registration, settings and help.
struct FormPage<Content: View>: View {
    let title: String
    @ViewBuilder var content: Content
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Metrics.roomy) { content }
                .frame(maxWidth: Metrics.formWidth, alignment: .leading)
                .padding(Metrics.roomy)
                .frame(maxWidth: .infinity)
        }
        .scrollDismissesKeyboard(.interactively)
        .background(GlassBackdrop())
        .navigationTitle(title).inlineNavigationTitle()
    }
}

struct NoticePanel: View {
    @Environment(\.palette) private var palette
    let title: String, message: String, detail: String?
    var body: some View {
        VStack(alignment: .leading, spacing: Metrics.tight) {
            Label(title, systemImage: "exclamationmark.triangle").font(.headline).foregroundColor(palette.danger)
            Text(message).font(.body).foregroundColor(palette.text).fixedSize(horizontal: false, vertical: true)
            if let detail { Text(detail).font(.footnote).foregroundColor(palette.muted).textSelection(.enabled) }
        }
        .padding(Metrics.standard).frame(maxWidth: .infinity, alignment: .leading)
        .glassPanel(.support, outline: palette.danger)
        .accessibilityElement(children: .combine)
    }
}

struct AddConsoleView: View {
    private enum Field { case host, name }
    @Environment(\.palette) private var palette
    @Environment(\.dynamicTypeSize) private var typeSize
    @Binding var path: [Route]
    @State private var draft = ConsoleDraft()
    @State private var attempted = false
    @FocusState private var focus: Field?

    private var host: String? { RegistrationInput.host(draft.host) }

    var body: some View {
        FormPage(title: "Add console") {
            Text("Enter your console's address on the local network. GameRemote does not search for consoles.")
                .font(.body).foregroundColor(palette.muted).fixedSize(horizontal: false, vertical: true)
            FieldChrome(label: "Console address", helper: "IP address or hostname, for example 192.168.1.20.",
                        error: attempted && host == nil ? "Enter an IP address or hostname without spaces." : nil) {
                TextField("Console address", text: $draft.host, prompt: Text(""))
                    .accessibilityIdentifier("console.address")
                    .addressInput().focused($focus, equals: .host).submitLabel(.next).onSubmit { focus = .name }
            }
            VStack(alignment: .leading, spacing: Metrics.tight) {
                Text("Console type").font(.subheadline.weight(.semibold)).foregroundColor(palette.text).accessibilityHidden(true)
                // Segments do not grow with text size; the menu style does.
                if typeSize.isAccessibilitySize { kindPicker.pickerStyle(.menu) } else { kindPicker.pickerStyle(.segmented) }
            }
            FieldChrome(label: "Name (optional)", helper: "Shown in your console list. The address is used when left empty.", error: nil) {
                TextField("Name", text: $draft.name, prompt: Text(""))
                    .accessibilityIdentifier("console.name")
                    .focused($focus, equals: .name).submitLabel(.continue).onSubmit(next)
            }
            // Stays enabled: activating it explains what is missing instead of a silent dimmed control.
            Button("Next", action: next).buttonStyle(GlassButtonStyle())
                .accessibilityIdentifier("console.next")
        }
        .toolbar {
            ToolbarItemGroup(placement: .keyboard) {
                Spacer()
                Button("Done") { focus = nil }
                    .accessibilityIdentifier("console.keyboard-done")
            }
        }
    }

    private var kindPicker: some View {
        Picker("Console type", selection: $draft.kind) {
            ForEach(ConsoleKind.allCases, id: \.self) { Text($0.title).tag($0) }
        }
        .frame(minHeight: Metrics.minimumTarget)
    }

    private func next() {
        attempted = true
        guard let host else { focus = .host; return }
        var committed = draft; committed.host = host
        focus = nil
        path.append(.register(committed))
    }
}

struct RegisterView: View {
    private enum Field { case account, code }
    @EnvironmentObject private var model: SessionModel
    @Environment(\.palette) private var palette
    @Binding var path: [Route]
    let draft: ConsoleDraft
    @State private var account = ""
    @State private var pairingCode = ""
    @State private var attempted = false
    @FocusState private var focus: Field?

    private var accountData: Data? { RegistrationInput.account(account) }
    private var pin: UInt32? { RegistrationInput.pairingCode(pairingCode) }
    // Back is withheld while native cleanup is pending and once the result replaces the form.
    private var hidesBack: Bool {
        switch model.phase { case .registering, .stopping, .registered: return true; default: return false }
    }

    var body: some View {
        FormPage(title: "Register console") {
            switch model.phase {
            case .registering: progress("Registering…", note: "Keep the Link Device screen open on your console.", cancellable: true)
            case .stopping: progress("Cancelling…", note: nil, cancellable: false)
            case .registered(let console): success(console)
            default: form
            }
        }
        .navigationBarBackButtonHidden(hidesBack)
        .onChange(of: model.phase) { phase in
            switch phase {
            case .registering: Platform.announce("Registering")
            case .registered: Platform.announce("Console registered")
            case .registrationFailed(let failure):
                // Announce after the focus move so the reason is not cut off by the field being read.
                focus = .code
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) { Platform.announce(SessionCopy.message(for: failure)) }
            default: break
            }
        }
    }

    @ViewBuilder private var form: some View {
        if case .registrationFailed(let failure) = model.phase {
            NoticePanel(title: "Registration failed", message: SessionCopy.message(for: failure), detail: SessionCopy.detail(for: failure))
        }
        HStack(alignment: .top, spacing: Metrics.related) {
            VStack(alignment: .leading, spacing: Metrics.detail) {
                Text(RegistrationInput.name(draft.name, host: draft.host)).font(.headline).foregroundColor(palette.text)
                Text("\(draft.kind.title) · \(draft.host)").font(.subheadline).foregroundColor(palette.muted)
            }
            .accessibilityElement(children: .combine)
            Spacer(minLength: 0)
            // A saved console keeps its address: it is the Keychain lookup key.
            if path.dropLast().last == .addConsole {
                Button("Edit") { path.removeLast() }.buttonStyle(GlassButtonStyle(kind: .secondary, fill: false)).accessibilityLabel("Edit address and console type")
            }
        }
        .padding(Metrics.standard).frame(maxWidth: .infinity, alignment: .leading).glassPanel(.support)

        FieldChrome(label: "PSN account ID", helper: "Use the base64 account identifier for this console account. It must decode to eight bytes.",
                    error: attempted && accountData == nil ? "Enter a base64 account ID that decodes to eight bytes." : nil) {
            TextField("PSN account ID", text: $account, prompt: Text(""))
                .accessibilityIdentifier("registration.account")
                .identifierInput().focused($focus, equals: .account).submitLabel(.next).onSubmit { focus = .code }
        }
        FieldChrome(label: "Console pairing code", helper: "Enter the eight-digit code shown in your console's Link Device screen.",
                    error: attempted && pin == nil ? "The pairing code is exactly eight digits." : nil) {
            SecureField("Console pairing code", text: $pairingCode, prompt: Text(""))
                .accessibilityIdentifier("registration.pairing-code")
                .digitInput().focused($focus, equals: .code).submitLabel(.go).onSubmit(submit)
        }
        Button("Register console", action: submit).buttonStyle(GlassButtonStyle())
            .accessibilityIdentifier("registration.submit")
            .disabled(!model.phase.allowsNewOperation)
        Button("Setup help") { path.append(.help) }.buttonStyle(GlassButtonStyle(kind: .secondary))
            .toolbar { ToolbarItemGroup(placement: .keyboard) { Spacer(); Button("Done") { focus = nil } } }
    }

    private func progress(_ title: String, note: String?, cancellable: Bool) -> some View {
        VStack(alignment: .leading, spacing: Metrics.standard) {
            HStack(spacing: Metrics.related) {
                ProgressView()
                Text(title).font(.headline).foregroundColor(palette.text)
            }
            .accessibilityElement(children: .combine)
            if let note { Text(note).font(.body).foregroundColor(palette.muted).fixedSize(horizontal: false, vertical: true) }
            if cancellable { Button("Cancel") { model.stop() }.buttonStyle(GlassButtonStyle(kind: .secondary)) }
        }
        .padding(Metrics.standard).frame(maxWidth: .infinity, alignment: .leading).glassPanel(.stage)
    }

    private func success(_ console: SavedConsole) -> some View {
        VStack(alignment: .leading, spacing: Metrics.standard) {
            StatusLabel(text: "Console registered", tone: .success)
            Text("“\(console.name)” is saved. Its credentials are stored in this device's Keychain.")
                .font(.body).foregroundColor(palette.text).fixedSize(horizontal: false, vertical: true)
            Button("Connect") {
                // Let the pop finish before the stream cover is presented over it.
                path.removeAll()
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.45) { model.connect(console) }
            }
            .buttonStyle(GlassButtonStyle())
            Button("Done") { path.removeAll() }.buttonStyle(GlassButtonStyle(kind: .secondary))
        }
        .padding(Metrics.standard).frame(maxWidth: .infinity, alignment: .leading).glassPanel(.stage)
    }

    private func submit() {
        attempted = true
        guard let accountData else { focus = .account; return }
        guard let pin else { focus = .code; return }
        focus = nil
        // The submitted code is not kept; a failed attempt needs a new one from the console.
        pairingCode = ""; attempted = false
        model.register(RegistrationRequest(name: RegistrationInput.name(draft.name, host: draft.host), host: draft.host, kind: draft.kind, account: accountData, pin: pin))
    }
}
