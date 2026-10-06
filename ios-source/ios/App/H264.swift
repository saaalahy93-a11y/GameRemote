import Foundation
// The core provides Annex B headers/access units; VideoToolbox consumes length-prefixed NALs.
enum H264 {
    static func nals(_ data: Data) -> [Data] {
        let bytes = [UInt8](data); var starts: [(Int, Int)] = []; var i = 0
        while i + 2 < bytes.count {
            if bytes[i] == 0 && bytes[i + 1] == 0 {
                if bytes[i + 2] == 1 { starts.append((i, i + 3)); i += 3; continue }
                if i + 3 < bytes.count && bytes[i + 2] == 0 && bytes[i + 3] == 1 { starts.append((i, i + 4)); i += 4; continue }
            }
            i += 1
        }
        return starts.enumerated().compactMap { index, start in
            let end = index + 1 < starts.count ? starts[index + 1].0 : bytes.count
            return end > start.1 ? Data(bytes[start.1..<end]) : nil
        }
    }
    static func avcc(_ nals: [Data]) -> Data {
        var output = Data()
        for nal in nals { var size = UInt32(nal.count).bigEndian; withUnsafeBytes(of: &size) { output.append(contentsOf: $0) }; output.append(nal) }
        return output
    }
}
