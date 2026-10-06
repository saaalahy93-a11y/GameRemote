import SwiftUI

// On-screen gamepad. Every control writes to the shared InputAggregator; gesture state resets on
// release and on cancellation, so a control cannot stay held after the touch goes away.
struct TouchControls: View {
    let input: InputAggregator
    // Leaves room for the stream menu button when the controls overlay the video.
    var topInset: CGFloat = 0
    var body: some View {
        GeometryReader { proxy in
            let layout = TouchControlLayout(size: proxy.size, topInset: topInset)
            VStack(spacing: layout.spacing) {
                HStack(spacing: Metrics.tight) {
                    trigger("L2", name: "L2", left: true); key("L1", name: "L1", .l1, compact: true)
                    Spacer(minLength: Metrics.tight)
                    if layout.style != .stacked { system(compact: layout.compact) }
                    Spacer(minLength: Metrics.tight)
                    key("R1", name: "R1", .r1, compact: true); trigger("R2", name: "R2", left: false)
                }
                if layout.style == .stacked { system(compact: false) }
                Spacer(minLength: 0)
                if layout.style == .expanded {
                    HStack(alignment: .bottom, spacing: Metrics.related) {
                        DirectionPad(input: input); stick(left: true, diameter: layout.stickDiameter); key("L3", name: "L3", .l3, compact: true)
                        Spacer(minLength: 0)
                        key("R3", name: "R3", .r3, compact: true); stick(left: false, diameter: layout.stickDiameter); FaceButtons(input: input, diameter: layout.faceDiameter)
                    }
                } else if layout.compact {
                    HStack(alignment: .bottom, spacing: Metrics.tight) {
                        DirectionPad(input: input)
                        VStack(spacing: Metrics.tight) {
                            key("L3", name: "L3", .l3, compact: true)
                            stick(left: true, diameter: layout.stickDiameter)
                        }
                        .frame(maxWidth: .infinity)
                        VStack(spacing: Metrics.tight) {
                            key("R3", name: "R3", .r3, compact: true)
                            stick(left: false, diameter: layout.stickDiameter)
                        }
                        .frame(maxWidth: .infinity)
                        FaceButtons(input: input, diameter: layout.faceDiameter)
                    }
                } else {
                    HStack(alignment: .center, spacing: Metrics.detail) { DirectionPad(input: input); Spacer(minLength: 0); FaceButtons(input: input, diameter: layout.faceDiameter) }
                    HStack(alignment: .center, spacing: Metrics.tight) {
                        stick(left: true, diameter: layout.stickDiameter); key("L3", name: "L3", .l3, compact: true)
                        Spacer(minLength: 0)
                        key("R3", name: "R3", .r3, compact: true); stick(left: false, diameter: layout.stickDiameter)
                    }
                }
            }
            .padding(Metrics.related).padding(.top, topInset)
        }
        .onDisappear { input.releaseTouch() }
    }

    private func system(compact: Bool) -> some View {
        HStack(spacing: Metrics.tight) {
            key(compact ? "Cr" : "Create", name: "Create", .create, compact: compact); key("Pad", name: "Touchpad button", .touchpad, compact: compact)
            key("PS", name: "PS", .ps, compact: compact); key(compact ? "Opt" : "Options", name: "Options", .options, compact: compact)
        }
    }
    private func key(_ label: String, name: String, _ button: PadButton, compact: Bool = false) -> some View {
        PadKey(name: name, diameter: compact ? TouchControlLayout.target : nil) { Text(label) } action: { input.setButton(button, pressed: $0) }
    }
    private func trigger(_ label: String, name: String, left: Bool) -> some View {
        PadKey(name: name, diameter: TouchControlLayout.target) { Text(label) } action: { input.setTrigger(left: left, pressed: $0) }
    }
    private func stick(left: Bool, diameter: CGFloat) -> some View {
        TouchStick(name: left ? "Left stick" : "Right stick", diameter: diameter) { input.setStick(left: left, x: $0, y: $1) }
    }
}

private enum PadChrome {
    static let fill = Color.black.opacity(0.55), pressedFill = Color.white.opacity(0.34)
    static let stroke = Color.white.opacity(0.6), label = Color.white
    static let font = Font.system(size: 15, weight: .semibold)
}

private struct PadKey<Label: View>: View {
    let name: String
    var round = false
    var diameter: CGFloat?
    @ViewBuilder var label: Label
    let action: (Bool) -> Void
    @GestureState private var pressed = false
    var body: some View {
        // A capsule with equal sides is the round face-button outline.
        label
            .font(PadChrome.font).foregroundColor(PadChrome.label)
            .padding(.horizontal, round || diameter != nil ? 0 : Metrics.related)
            .frame(minWidth: diameter ?? (round ? 52 : Metrics.minimumTarget), minHeight: diameter ?? (round ? 52 : Metrics.minimumTarget))
            .frame(width: diameter, height: diameter)
            .background(Capsule().fill(pressed ? PadChrome.pressedFill : PadChrome.fill))
            .overlay(Capsule().strokeBorder(PadChrome.stroke, lineWidth: 1))
            .contentShape(Capsule())
            .gesture(DragGesture(minimumDistance: 0).updating($pressed) { _, state, _ in state = true })
            .onChange(of: pressed) { action($0) }
            .accessibilityElement().accessibilityLabel(name)
            .accessibilityAddTraits([.isButton, .allowsDirectInteraction])
    }
}

private struct FaceButtons: View {
    let input: InputAggregator
    let diameter: CGFloat
    var body: some View {
        VStack(spacing: 0) {
            face("triangle", name: "Triangle", .triangle)
            HStack(spacing: 44) { face("square", name: "Square", .square); face("circle", name: "Circle", .circle) }
            face("xmark", name: "Cross", .cross)
        }
    }
    private func face(_ symbol: String, name: String, _ button: PadButton) -> some View {
        PadKey(name: name, round: true, diameter: diameter) { Image(systemName: symbol) } action: { input.setButton(button, pressed: $0) }
    }
}

// One surface for all four directions so a thumb can roll through diagonals.
private struct DirectionPad: View {
    let input: InputAggregator
    @GestureState private var location: CGPoint?
    private static let side = TouchControlLayout.directionSide, deadZone: CGFloat = 12
    var body: some View {
        let held = Self.directions(at: location)
        ZStack {
            Circle().fill(PadChrome.fill).overlay(Circle().strokeBorder(PadChrome.stroke, lineWidth: 1))
            arrow("arrowtriangle.up.fill", .dpadUp, held).offset(y: -40)
            arrow("arrowtriangle.down.fill", .dpadDown, held).offset(y: 40)
            arrow("arrowtriangle.left.fill", .dpadLeft, held).offset(x: -40)
            arrow("arrowtriangle.right.fill", .dpadRight, held).offset(x: 40)
        }
        .frame(width: Self.side, height: Self.side).contentShape(Circle())
        .gesture(DragGesture(minimumDistance: 0).updating($location) { value, state, _ in state = value.location })
        .onChange(of: held) { now in
            for button in [PadButton.dpadUp, .dpadDown, .dpadLeft, .dpadRight] { input.setButton(button, pressed: now & button.rawValue != 0) }
        }
        .accessibilityElement().accessibilityLabel("Directional pad")
        .accessibilityAddTraits(.allowsDirectInteraction)
    }
    private func arrow(_ symbol: String, _ button: PadButton, _ held: UInt32) -> some View {
        Image(systemName: symbol).font(PadChrome.font).foregroundColor(PadChrome.label.opacity(held & button.rawValue != 0 ? 1 : 0.8))
    }
    static func directions(at location: CGPoint?) -> UInt32 {
        guard let location else { return 0 }
        return PadGeometry.directions(dx: Double(location.x - side / 2), dy: Double(location.y - side / 2), deadZone: Double(deadZone))
    }
}

private struct TouchStick: View {
    let name: String
    let diameter: CGFloat
    let update: (Double, Double) -> Void
    @GestureState private var translation = CGSize.zero
    private static let knob: CGFloat = 48
    var body: some View {
        let radius = (diameter - Self.knob) / 2
        let length = (translation.width * translation.width + translation.height * translation.height).squareRoot()
        let scale = length > radius ? radius / length : 1
        ZStack {
            Circle().fill(PadChrome.fill).overlay(Circle().strokeBorder(PadChrome.stroke, lineWidth: 1))
            Circle().fill(PadChrome.pressedFill).overlay(Circle().strokeBorder(PadChrome.stroke, lineWidth: 1))
                .frame(width: Self.knob, height: Self.knob)
                .offset(x: translation.width * scale, y: translation.height * scale)
        }
        .frame(width: diameter, height: diameter).contentShape(Circle())
        .gesture(DragGesture(minimumDistance: 0).updating($translation) { value, state, _ in state = value.translation })
        .onChange(of: translation) { now in update(Double(now.width / radius), Double(now.height / radius)) }
        .accessibilityElement().accessibilityLabel(name)
        .accessibilityAddTraits(.allowsDirectInteraction)
    }
}
