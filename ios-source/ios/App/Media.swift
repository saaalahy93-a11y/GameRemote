import AVFoundation
import VideoToolbox
import UIKit

final class VideoView: UIView {
    override class var layerClass: AnyClass { AVSampleBufferDisplayLayer.self }
    var display: AVSampleBufferDisplayLayer { layer as! AVSampleBufferDisplayLayer }
    override init(frame: CGRect) { super.init(frame: frame); display.videoGravity = .resizeAspect; backgroundColor = .black }
    required init?(coder: NSCoder) { fatalError("init(coder:) is unsupported") }
}

final class Media {
    let view = VideoView()
    private var format: CMVideoFormatDescription?
    private var formatVersion: UInt64?
    private let videoAdmission = VideoAdmission(capacity: 2)
    private let audioQueue = DispatchQueue(label: "audio")
    private let audioSlots = DispatchSemaphore(value: 8)
    private let engine = AVAudioEngine(), player = AVAudioPlayerNode()
    private let audioStartup = StartupCache<AudioConfiguration, AVAudioFormat>()
    var failure: ((String) -> Void)?
    init() { engine.attach(player) }
    // Two pending video callbacks at most; rejection asks the core for a recovery frame.
    func video(_ data: Data) -> Bool {
        switch videoAdmission.admit(H264.nals(data)) {
        case .header: return true // Store SPS/PPS even when both frame slots are occupied.
        case .rejected: return false
        case .frame(let frame):
            DispatchQueue.main.async { [self] in
                defer { videoAdmission.finish(frame) }
                display(frame)
            }
            return true
        }
    }
    private func display(_ frame: VideoAdmission.Frame) {
        guard videoAdmission.canDisplay(frame) else { return }
        let nals = frame.nals
        if formatVersion != frame.configuration.version {
            view.display.flush(); format = nil; formatVersion = nil
            let sps = frame.configuration.sps, pps = frame.configuration.pps
            let status = sps.withUnsafeBytes { s in pps.withUnsafeBytes { p in
                let pointers = [s.bindMemory(to: UInt8.self).baseAddress!, p.bindMemory(to: UInt8.self).baseAddress!]
                let sizes = [sps.count, pps.count]
                return CMVideoFormatDescriptionCreateFromH264ParameterSets(allocator: nil, parameterSetCount: 2, parameterSetPointers: pointers, parameterSetSizes: sizes, nalUnitHeaderLength: 4, formatDescriptionOut: &format)
            } }
            guard status == noErr else { videoAdmission.drop(frame); failure?("Invalid H.264 configuration (\(status))"); return }
            formatVersion = frame.configuration.version
        }
        let frames = nals.filter { guard let b = $0.first else { return false }; return b & 31 != 7 && b & 31 != 8 }
        guard !frames.isEmpty, let format else { return }
        if view.display.status == .failed { videoAdmission.drop(frame); failure?("Video decode failed"); view.display.flush(); return }
        guard view.display.isReadyForMoreMediaData else { videoAdmission.drop(frame); return }
        let payload = H264.avcc(frames); var block: CMBlockBuffer?
        guard CMBlockBufferCreateWithMemoryBlock(allocator: nil, memoryBlock: nil, blockLength: payload.count, blockAllocator: nil, customBlockSource: nil, offsetToData: 0, dataLength: payload.count, flags: 0, blockBufferOut: &block) == noErr, let block else { videoAdmission.drop(frame); return }
        let copied = payload.withUnsafeBytes { CMBlockBufferReplaceDataBytes(with: $0.baseAddress!, blockBuffer: block, offsetIntoDestination: 0, dataLength: payload.count) }
        guard copied == noErr else { videoAdmission.drop(frame); return }
        var sample: CMSampleBuffer?; var size = payload.count
        guard CMSampleBufferCreateReady(allocator: nil, dataBuffer: block, formatDescription: format, sampleCount: 1, sampleTimingEntryCount: 0, sampleTimingArray: nil, sampleSizeEntryCount: 1, sampleSizeArray: &size, sampleBufferOut: &sample) == noErr, let sample else { videoAdmission.drop(frame); return }
        if let attachments = CMSampleBufferGetSampleAttachmentsArray(sample, createIfNecessary: true) {
            let dictionary = unsafeBitCast(CFArrayGetValueAtIndex(attachments, 0), to: CFMutableDictionary.self)
            CFDictionarySetValue(dictionary, Unmanaged.passUnretained(kCMSampleAttachmentKey_DisplayImmediately).toOpaque(), Unmanaged.passUnretained(kCFBooleanTrue).toOpaque())
        }
        // AVSampleBufferDisplayLayer performs H.264 decoding via the system VideoToolbox pipeline.
        videoAdmission.display(frame) { view.display.enqueue(sample) }
    }
    func audio(_ data: Data, frames: Int, channels: UInt32, rate: UInt32) {
        guard audioSlots.wait(timeout: .now()) == .success else { return }
        audioQueue.async { [weak self] in
            guard let self else { return }
            guard channels > 0, channels <= 2, frames > 0,
                  data.count == frames * Int(channels) * 2 else { self.audioSlots.signal(); return }
            do {
                let format = try self.audioStartup.ensure(AudioConfiguration(channels: channels, rate: rate), running: self.engine.isRunning && self.player.isPlaying, reset: {
                    self.player.stop(); self.engine.stop(); self.engine.reset()
                    self.engine.disconnectNodeOutput(self.player)
                }, start: {
                    let session = AVAudioSession.sharedInstance()
                    try session.setCategory(.playback, mode: .default); try session.setActive(true)
                    guard let format = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: Double(rate), channels: channels, interleaved: false) else { throw MediaError.audioFormat }
                    self.engine.connect(self.player, to: self.engine.mainMixerNode, format: format)
                    try self.engine.start(); self.player.play()
                    return format
                })
                guard let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(frames)), let outputs = buffer.floatChannelData else { self.audioSlots.signal(); return }
                buffer.frameLength = AVAudioFrameCount(frames)
                data.withUnsafeBytes { raw in
                    for channel in 0..<Int(channels) { for frame in 0..<frames {
                        let sample = raw.loadUnaligned(fromByteOffset: (frame * Int(channels) + channel) * 2, as: Int16.self)
                        outputs[channel][frame] = Float(sample) / 32768
                    } }
                }
                self.player.scheduleBuffer(buffer, completionCallbackType: .dataPlayedBack) { [weak self] _ in self?.audioSlots.signal() }
            } catch { self.audioSlots.signal(); DispatchQueue.main.async { self.failure?("Audio output failed: \(error.localizedDescription)") } }
        }
    }
    private enum MediaError: Error { case audioFormat }
    func stop() {
        videoAdmission.reset()
        DispatchQueue.main.async { self.view.display.flushAndRemoveImage(); self.format = nil; self.formatVersion = nil }
        audioQueue.async {
            self.player.stop(); self.engine.stop(); self.engine.reset(); self.audioStartup.clear()
            do {
                try AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
            } catch {
                DispatchQueue.main.async { self.failure?("Audio session could not be released: \(error.localizedDescription)") }
            }
        }
    }
}
