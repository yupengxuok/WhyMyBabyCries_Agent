import AVFoundation

enum AudioPCMConverter {
    static func int16Data(from buffer: AVAudioPCMBuffer) -> Data? {
        guard let channelData = buffer.floatChannelData?[0] else { return nil }
        let frameLength = Int(buffer.frameLength)
        if frameLength == 0 { return nil }

        var int16Buffer = [Int16](repeating: 0, count: frameLength)
        for i in 0..<frameLength {
            let sample = max(-1.0, min(1.0, channelData[i]))
            int16Buffer[i] = Int16(sample * 32767.0)
        }
        return Data(bytes: int16Buffer, count: int16Buffer.count * MemoryLayout<Int16>.size)
    }
}
