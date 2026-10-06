"""Check shared media APIs with macOS SDK, substituting UIView and AVAudioSession.
This generated collaborator is never app source or a substitute for iOS compilation.
"""
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
source = (root / 'ios/App/Media.swift').read_text().replace('import UIKit', 'import QuartzCore')
start = source.index('final class VideoView: UIView {')
end = source.index('\nfinal class Media {', start)
source = source[:start] + 'final class VideoView { let display = AVSampleBufferDisplayLayer() }\n' + source[end:]
# Keep both activation and deactivation control flow in the host typecheck. This stub only
# mirrors their signatures; it cannot establish any iOS audio-session runtime behavior.
source += '''
private final class AVAudioSession {
    enum Category { case playback }
    enum Mode { case `default` }
    struct SetActiveOptions: OptionSet {
        let rawValue: Int
        static let notifyOthersOnDeactivation = SetActiveOptions(rawValue: 1)
    }
    static func sharedInstance() -> AVAudioSession { AVAudioSession() }
    func setCategory(_ category: Category, mode: Mode) throws {}
    func setActive(_ active: Bool, options: SetActiveOptions = []) throws {}
}
'''
Path(sys.argv[1]).write_text(source)
