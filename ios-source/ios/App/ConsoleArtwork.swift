import SwiftUI

// Minimal SVG path-data reader for the console silhouettes (M L H V C Z, absolute and relative).
enum SVGPath {
    static func parse(_ data: String) -> Path {
        var path = Path(), numbers: [CGFloat] = [], command: Character = "M", token = ""
        var current = CGPoint.zero, start = CGPoint.zero
        func flushToken() { if let value = Double(token) { numbers.append(CGFloat(value)) }; token = "" }
        func apply() {
            let relative = command.isLowercase
            func point(_ x: CGFloat, _ y: CGFloat) -> CGPoint { relative ? CGPoint(x: current.x + x, y: current.y + y) : CGPoint(x: x, y: y) }
            switch command.uppercased() {
            case "M":
                guard numbers.count >= 2 else { return }
                current = point(numbers[0], numbers[1]); start = current; path.move(to: current); numbers.removeFirst(2)
                command = relative ? "l" : "L" // further pairs are implicit line-tos
            case "L":
                guard numbers.count >= 2 else { return }
                current = point(numbers[0], numbers[1]); path.addLine(to: current); numbers.removeFirst(2)
            case "H":
                guard numbers.count >= 1 else { return }
                current = CGPoint(x: relative ? current.x + numbers[0] : numbers[0], y: current.y); path.addLine(to: current); numbers.removeFirst(1)
            case "V":
                guard numbers.count >= 1 else { return }
                current = CGPoint(x: current.x, y: relative ? current.y + numbers[0] : numbers[0]); path.addLine(to: current); numbers.removeFirst(1)
            case "C":
                guard numbers.count >= 6 else { return }
                let c1 = point(numbers[0], numbers[1]), c2 = point(numbers[2], numbers[3]), end = point(numbers[4], numbers[5])
                path.addCurve(to: end, control1: c1, control2: c2); current = end; numbers.removeFirst(6)
            default: numbers.removeAll()
            }
        }
        func drain() { var previous = -1; while !numbers.isEmpty && numbers.count != previous { previous = numbers.count; apply() }; numbers.removeAll() }
        for character in data {
            if character.isLetter && character != "e" && character != "E" {
                flushToken(); drain()
                if character == "Z" || character == "z" { path.closeSubpath(); current = start } else { command = character }
            } else if character == "," || character.isWhitespace {
                flushToken()
            } else if character == "-" && !token.isEmpty && token.last != "e" && token.last != "E" {
                flushToken(); token.append(character)
            } else {
                token.append(character)
            }
        }
        flushToken(); drain()
        return path
    }
}

// Neutral device artwork from gui/res/console-ps5.svg and console-ps4.svg. The indicator-light
// layers are omitted: this app has no console power state to show.
struct ConsoleSilhouette: View {
    @Environment(\.palette) private var palette
    let kind: ConsoleKind
    static let ps5 = (size: CGSize(width: 135.46666, height: 35.983334), path: SVGPath.parse("M 135.059,0.00361735 C 105.38,2.67905 69.7613,6.71862 7.63725,2.23759 2.36805,1.85752 -2.0101,10.5297 0.965315,10.4913 65.3799,9.66192 117.287,1.77461 124.96,2.9347 c 1.336,0.20209 1.574,0.63399 2.277,3.27111 0.014,0.05608 0.023,0.07751 0.037,0.12971 C 127.222,6.33518 127.18,6.33367 127.127,6.33346 111.134,6.26936 42.5958,12.2796 1.90841,11.7636 V 19.744 C 42.7269,19.2263 111.141,25.2757 127.21,25.1721 c -0.021,0.0757 -0.034,0.1108 -0.056,0.1953 -0.703,2.6371 -0.941,3.069 -2.278,3.2711 C 117.203,29.7986 65.8099,22.0167 1.39526,21.1873 0.890231,21.1808 0.0271625,21.6584 0.0697631,22.3945 0.299552,26.3647 0.436565,35.8186 1.11931,35.8195 c 9.35179,0.0128 30.51999,0.601 40.77269,-0.5323 18.7057,-2.0678 32.929,-4.7279 44.5021,-5.3898 21.5319,-1.2316 33.9069,0.0527 48.5829,1.6722 0.933,0.103 0.031,-1.2457 -0.448,-1.2407 -1.987,0.0225 -4.222,-2.7307 -6.798,-4.992 -0.019,-0.0164 -0.028,-0.0822 -0.032,-0.1741 1.321,-0.0216 2.268,-0.0875 2.695,-0.2171 V 16.0465 15.4616 6.56238 c -0.424,-0.12876 -1.327,-0.19659 -2.607,-0.21859 0.006,-0.05334 0.013,-0.09568 0.027,-0.10749 2.576,-2.26123 4.811,-5.01452 6.797,-4.99193 0.479,0.005 1.384,-1.3250825 0.448,-1.24075265 z"))
    static let ps4 = (size: CGSize(width: 135.46666, height: 22.754167), path: SVGPath.parse("M 13.5375,-1.8e-4 7.93029,9.42447 H 129.859 l 5.608,-9.42465 z M 5.60643,13.3301 -3.72927e-7,22.754 H 121.929 l 5.607,-9.4239 z"))
    var body: some View {
        let art = kind == .ps5 ? Self.ps5 : Self.ps4
        GeometryReader { proxy in
            let scale = min(proxy.size.width / art.size.width, proxy.size.height / art.size.height)
            let fitted = CGSize(width: art.size.width * scale, height: art.size.height * scale)
            art.path.applying(CGAffineTransform(scaleX: scale, y: scale))
                .fill(LinearGradient(colors: [palette.text.opacity(0.92), palette.muted.opacity(0.78)], startPoint: .top, endPoint: .bottom))
                .frame(width: fitted.width, height: fitted.height)
                .position(x: proxy.size.width / 2, y: proxy.size.height / 2)
        }
        .accessibilityHidden(true)
    }
}
