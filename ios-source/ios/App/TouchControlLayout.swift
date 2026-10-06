import Foundation

// GeometryReader supplies the safe-area content size, not the device's screen bounds.
// These dimensions are also the dimensions used by the controls, so layout decisions account
// for the whole row rather than a device/orientation breakpoint.
struct TouchControlLayout {
    enum Style { case expanded, compact, stacked }
    static let inset: CGFloat = 12, gap: CGFloat = 8, target: CGFloat = 44
    static let directionSide: CGFloat = 132
    let style: Style
    let stickDiameter: CGFloat

    init(size: CGSize, topInset: CGFloat) {
        let height = max(0, size.height - topInset)
        if size.width >= Self.expandedSize.width && height >= Self.expandedSize.height {
            style = .expanded; stickDiameter = 104
        } else if size.width >= Self.compactSize.width && (size.width > height || height < 420) {
            style = .compact; stickDiameter = 80
        } else {
            style = .stacked; stickDiameter = size.width >= 352 ? 104 : 80
        }
    }

    var compact: Bool { style == .compact }
    var faceDiameter: CGFloat { compact ? Self.target : 52 }
    var faceSize: CGSize { CGSize(width: faceDiameter * 2 + 44, height: faceDiameter * 3) }
    var spacing: CGFloat { compact ? Self.gap : Self.inset }
    var minimumSize: CGSize {
        switch style {
        case .expanded: return Self.expandedSize
        case .compact: return Self.compactSize
        case .stacked:
            return CGSize(width: max(Self.directionSide + 8 + faceSize.width, 2 * stickDiameter + 2 * Self.target + 4 * Self.gap) + 2 * Self.inset,
                          height: 2 * Self.target + faceSize.height + stickDiameter + 4 * Self.inset + 2 * Self.inset)
        }
    }

    private static var expandedSize: CGSize {
        CGSize(width: directionSide + 2 * 104 + 2 * target + 148 + 6 * inset + 2 * inset,
               height: target + 2 * inset + 156 + 2 * inset)
    }
    private static var compactSize: CGSize {
        CGSize(width: directionSide + 2 * 80 + 132 + 3 * gap + 2 * inset,
               height: target + 2 * gap + 132 + 2 * inset)
    }
}
