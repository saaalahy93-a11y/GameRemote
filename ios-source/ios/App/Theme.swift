import SwiftUI

// Broadcast desk / optical glass. Values come from docs/design/platform-tokens.json;
// translucent entries were converted from the Android #AARRGGBB resources.
struct Palette: Equatable {
    let canvas, ambient, ground: Color
    let panelTop, panelBottom, supportTop, supportBottom: Color
    let field, control, raised: Color
    let text, muted, disabled, border, edge, glint: Color
    let accent, onAccent, danger, success: Color

    static let dark = Palette(
        canvas: Color(hex: 0x080F19), ambient: Color(hex: 0x17384B), ground: Color(hex: 0x101A2B),
        panelTop: Color(hex: 0x2A455B, alpha: 0.90), panelBottom: Color(hex: 0x172B3D, alpha: 0.94),
        supportTop: Color(hex: 0x2C4559, alpha: 0.85), supportBottom: Color(hex: 0x17293B, alpha: 0.92),
        field: Color(hex: 0x172B3D), control: Color(hex: 0x1E3348, alpha: 0.70), raised: Color(hex: 0x20394C),
        text: Color(hex: 0xF1F6FA), muted: Color(hex: 0xB4C5D2), disabled: Color(hex: 0x718696), border: Color(hex: 0x52728A),
        edge: Color(hex: 0x88B2C8, alpha: 0.40), glint: Color(hex: 0xD3F0FF, alpha: 0.60),
        accent: Color(hex: 0x78D8EC), onAccent: Color(hex: 0x082631), danger: Color(hex: 0xFFB4AB), success: Color(hex: 0x8ED7B4))
    static let light = Palette(
        canvas: Color(hex: 0xE8EFF5), ambient: Color(hex: 0xD7E8F2), ground: Color(hex: 0xE8EFF5),
        panelTop: Color(hex: 0xFFFFFF, alpha: 0.94), panelBottom: Color(hex: 0xF5FAFE, alpha: 0.87),
        supportTop: Color(hex: 0xF6FBFF, alpha: 0.90), supportBottom: Color(hex: 0xE5EFF6, alpha: 0.87),
        field: Color(hex: 0xF7FBFE), control: Color(hex: 0xFFFFFF, alpha: 0.70), raised: Color(hex: 0xE4EEF5),
        text: Color(hex: 0x142A38), muted: Color(hex: 0x435F72), disabled: Color(hex: 0x8193A0), border: Color(hex: 0xA5BECD),
        edge: Color(hex: 0x8FABBE, alpha: 0.60), glint: Color(hex: 0xFFFFFF, alpha: 0.80),
        accent: Color(hex: 0x087A94), onAccent: Color(hex: 0xFFFFFF), danger: Color(hex: 0xB3261E), success: Color(hex: 0x216E4E))
}

extension Color {
    init(hex: UInt32, alpha: Double = 1) {
        self.init(.sRGB, red: Double((hex >> 16) & 0xFF) / 255, green: Double((hex >> 8) & 0xFF) / 255, blue: Double(hex & 0xFF) / 255, opacity: alpha)
    }
}

extension EnvironmentValues {
    var palette: Palette { colorScheme == .dark ? .dark : .light }
}

enum Metrics {
    static let detail: CGFloat = 4, tight: CGFloat = 8, related: CGFloat = 12, standard: CGFloat = 16, roomy: CGFloat = 24, section: CGFloat = 32
    static let controlRadius: CGFloat = 12, panelRadius: CGFloat = 16, minimumTarget: CGFloat = 44
    static let formWidth: CGFloat = 600
}

// Static canvas gradient. No blur, sampling or animation.
struct GlassBackdrop: View {
    @Environment(\.palette) private var palette
    var body: some View {
        LinearGradient(stops: [.init(color: palette.ambient, location: 0), .init(color: palette.canvas, location: 0.58), .init(color: palette.ground, location: 1)],
                       startPoint: .topLeading, endPoint: .bottomTrailing)
            .ignoresSafeArea()
    }
}

enum GlassRole { case stage, support }

private struct GlassPanel: ViewModifier {
    @Environment(\.palette) private var palette
    let role: GlassRole
    let outline: Color?
    func body(content: Content) -> some View {
        let shape = RoundedRectangle(cornerRadius: Metrics.panelRadius, style: .continuous)
        let top = role == .stage ? palette.panelTop : palette.supportTop, bottom = role == .stage ? palette.panelBottom : palette.supportBottom
        content
            .background(shape.fill(LinearGradient(colors: [top, bottom], startPoint: .top, endPoint: .bottom)))
            .overlay(shape.strokeBorder(outline ?? palette.edge, lineWidth: 1))
            // One-point glint across the inset upper edge.
            .overlay(alignment: .top) {
                LinearGradient(colors: [palette.glint.opacity(0), palette.glint, palette.glint.opacity(0)], startPoint: .leading, endPoint: .trailing)
                    .frame(height: 1).padding(.horizontal, Metrics.standard).padding(.top, 1).accessibilityHidden(true)
            }
    }
}

extension View {
    func glassPanel(_ role: GlassRole = .stage, outline: Color? = nil) -> some View { modifier(GlassPanel(role: role, outline: outline)) }
}

struct GlassButtonStyle: ButtonStyle {
    enum Kind { case primary, secondary, danger }
    var kind: Kind = .primary
    var fill = true
    func makeBody(configuration: Configuration) -> some View { Chrome(kind: kind, fill: fill, configuration: configuration) }

    private struct Chrome: View {
        @Environment(\.palette) private var palette
        @Environment(\.isEnabled) private var isEnabled
        let kind: Kind, fill: Bool, configuration: ButtonStyleConfiguration
        var body: some View {
            let shape = RoundedRectangle(cornerRadius: Metrics.controlRadius, style: .continuous)
            configuration.label
                .font(.body.weight(.semibold))
                .multilineTextAlignment(.center)
                .foregroundColor(isEnabled ? foreground : palette.disabled)
                .padding(.horizontal, Metrics.standard).padding(.vertical, Metrics.related)
                .frame(maxWidth: fill ? .infinity : nil, minHeight: Metrics.minimumTarget)
                .background(shape.fill(background).opacity(isEnabled ? 1 : 0.45))
                .overlay(shape.strokeBorder(kind == .primary ? palette.glint.opacity(0.35) : palette.edge, lineWidth: 1))
                .overlay(shape.fill(Color.black.opacity(configuration.isPressed ? 0.12 : 0)))
                .contentShape(shape)
        }
        private var foreground: Color {
            switch kind { case .primary: return palette.onAccent; case .secondary: return palette.text; case .danger: return palette.danger }
        }
        private var background: Color { kind == .primary ? palette.accent : palette.control }
    }
}

// Labelled field chrome: persistent label, helper text and an inline error below the control.
struct FieldChrome<Content: View>: View {
    @Environment(\.palette) private var palette
    @Environment(\.colorSchemeContrast) private var contrast
    let label: String, helper: String?, error: String?
    @ViewBuilder var content: Content
    var body: some View {
        VStack(alignment: .leading, spacing: Metrics.tight) {
            // The control carries the spoken label; its error or helper is read with it as the hint.
            Text(label).font(.subheadline.weight(.semibold)).foregroundColor(palette.text).accessibilityHidden(true)
            content
                .accessibilityLabel(label)
                .accessibilityHint(error ?? helper ?? "")
                .font(.body)
                .foregroundColor(palette.text)
                .padding(.horizontal, Metrics.related)
                .frame(minHeight: Metrics.minimumTarget)
                .background(RoundedRectangle(cornerRadius: Metrics.controlRadius, style: .continuous).fill(palette.field))
                .overlay(RoundedRectangle(cornerRadius: Metrics.controlRadius, style: .continuous).strokeBorder(error != nil ? palette.danger : contrast == .increased ? palette.muted : palette.border, lineWidth: error == nil ? 1 : 2))
            if let error {
                // Keep the visible error independently readable, including when spoken hints are disabled.
                Label(error, systemImage: "exclamationmark.circle").font(.footnote).foregroundColor(palette.danger).fixedSize(horizontal: false, vertical: true)
                    .accessibilityElement(children: .ignore).accessibilityLabel(error)
            } else if let helper {
                Text(helper).font(.footnote).foregroundColor(palette.muted).fixedSize(horizontal: false, vertical: true).accessibilityHidden(true)
            }
        }
    }
}

// Status always carries text; colour and symbol only support it.
struct StatusLabel: View {
    @Environment(\.palette) private var palette
    enum Tone { case neutral, success, danger }
    let text: String, tone: Tone
    var body: some View {
        Label(text, systemImage: tone == .success ? "checkmark.circle" : tone == .danger ? "exclamationmark.triangle" : "circle.dashed")
            .font(.subheadline).foregroundColor(tone == .success ? palette.success : tone == .danger ? palette.danger : palette.muted)
    }
}

// Connected-screen mark with the native wordmark. The image is decorative beside the text.
struct BrandLockup: View {
    @Environment(\.palette) private var palette
    var body: some View {
        HStack(spacing: Metrics.related) {
            Image("BrandMark").resizable().interpolation(.high).aspectRatio(1, contentMode: .fit).frame(width: 32, height: 32)
                .clipShape(RoundedRectangle(cornerRadius: 7, style: .continuous)).accessibilityHidden(true)
            Text("GameRemote").font(.headline).foregroundColor(palette.text)
        }
        .accessibilityElement(children: .combine).accessibilityAddTraits(.isHeader)
    }
}
