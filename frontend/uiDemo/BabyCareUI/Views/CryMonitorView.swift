import SwiftUI
import AVFoundation

enum MonitorStatus: String {
    case idle = "Ready"
    case listening = "Monitoring..."
    case active = "Engaged"
    case error = "Error"
}

final class CryMonitorViewModel: ObservableObject {
    @Published var status: MonitorStatus = .idle
    @Published var currentVolume: Float = 0
    @Published var threshold: Float = 0.15
    @Published var history: [String] = []
    @Published var errorMessage: String? = nil
    @Published var debugInfo: String = ""

    private let audioEngine = AVAudioEngine()
    private var inputFormat: AVAudioFormat?
    private var inputConverter: AVAudioConverter?
    private var targetInputFormat: AVAudioFormat?
    private let playerNode = AVAudioPlayerNode()
    private var outputFormat: AVAudioFormat?
    private var geminiClient: GeminiLiveClient?
    private var isSessionActive = false
    private var isSessionReady = false
    private var sentFrameCount = 0
    private var receivedAudioCount = 0
    private var receivedTranscriptCount = 0
    private let audioSendQueue = DispatchQueue(label: "babycare.audio.send.queue")
    private let sendStride = 3
    private var sendGateCounter = 0

    private let systemPrompt = """
    You are a warm, gentle, and musical nanny AI designed to soothe crying babies.
    When you detect distress, your goal is to immediately offer comfort.
    Rules:
    1. Use a soft, melodic, and rhythmic voice.
    2. Hum gentle lullabies or tell very short, calming stories about fluffy clouds and sleepy animals.
    3. Keep sentences short and repetitive (like "It's okay, little one", "Shhh, I am here").
    4. If the baby keeps crying, try a different approach: gentle singing or mimicking a heartbeat sound.
    5. Do not stop until the environment becomes quiet.
    """

    func startMonitoring() {
        errorMessage = nil
        status = .listening

        AVAudioSession.sharedInstance().requestRecordPermission { [weak self] granted in
            DispatchQueue.main.async {
                guard let self = self else { return }
                if !granted {
                    self.status = .error
                    self.errorMessage = "Microphone permission denied."
                    return
                }
                if self.apiKey.isEmpty || self.apiKey == "REPLACE_WITH_YOUR_API_KEY" {
                    self.status = .error
                    self.errorMessage = "Missing Gemini API key in Info.plist."
                    return
                }
                self.configureAndStartEngine()
            }
        }
    }

    func stopMonitoring() {
        audioEngine.inputNode.removeTap(onBus: 0)
        stopPlayback()
        geminiClient?.close()
        geminiClient = nil
        isSessionActive = false
        isSessionReady = false
        sentFrameCount = 0
        receivedAudioCount = 0
        receivedTranscriptCount = 0
        debugInfo = ""
        audioEngine.stop()
        status = .idle
        currentVolume = 0
    }

    private func configureAndStartEngine() {
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playAndRecord, mode: .measurement, options: [.defaultToSpeaker, .allowBluetooth])
            try session.setPreferredSampleRate(16000)
            try session.setActive(true, options: .notifyOthersOnDeactivation)

            let inputNode = audioEngine.inputNode
            let format = inputNode.outputFormat(forBus: 0)
            inputFormat = format
            targetInputFormat = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: 16000, channels: 1, interleaved: false)
            if let targetInputFormat = targetInputFormat {
                inputConverter = AVAudioConverter(from: format, to: targetInputFormat)
            }

            if playerNode.engine == nil {
                audioEngine.attach(playerNode)
                let outFormat = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: 24000, channels: 1, interleaved: false)
                outputFormat = outFormat
                audioEngine.connect(playerNode, to: audioEngine.mainMixerNode, format: outFormat)
            }

            inputNode.removeTap(onBus: 0)
            inputNode.installTap(onBus: 0, bufferSize: 8192, format: format) { [weak self] buffer, _ in
                self?.processAudioBuffer(buffer)
            }

            audioEngine.prepare()
            try audioEngine.start()
        } catch {
            status = .error
            errorMessage = "Failed to start audio engine."
        }
    }

    private func processAudioBuffer(_ buffer: AVAudioPCMBuffer) {
        guard let channelData = buffer.floatChannelData?[0] else { return }
        let frameLength = Int(buffer.frameLength)
        if frameLength == 0 { return }

        var sum: Float = 0
        for i in 0..<frameLength {
            let sample = channelData[i]
            sum += sample * sample
        }
        let rms = sqrt(sum / Float(frameLength))

        DispatchQueue.main.async {
            self.currentVolume = rms
            if self.status == .listening && !self.isSessionActive && (self.threshold == 0 || rms > self.threshold) {
                self.startGeminiSession()
                self.appendHistory("Cry detected. Comforting...")
            }
        }

        if isSessionActive {
            if let copied = copyBuffer(buffer) {
                audioSendQueue.async { [weak self] in
                    self?.sendAudioToGemini(buffer: copied)
                }
            }
        }
    }

    private func appendHistory(_ text: String) {
        history.append(text)
        if history.count > 10 {
            history.removeFirst(history.count - 10)
        }
    }

    private var apiKey: String {
        Bundle.main.object(forInfoDictionaryKey: "GEMINI_API_KEY") as? String ?? ""
    }

    private func startGeminiSession() {
        guard !apiKey.isEmpty else { return }

        let modelName = "models/gemini-2.5-flash-native-audio-preview-12-2025"
        let client = GeminiLiveClient(
            apiKey: apiKey,
            model: modelName,
            systemInstruction: systemPrompt,
            voiceName: "Kore"
        )

        client.onAudio = { [weak self] base64, mimeType in
            DispatchQueue.main.async {
                self?.receivedAudioCount += 1
                self?.updateDebugInfo()
                self?.playAudio(base64: base64, mimeType: mimeType)
            }
        }
        client.onInputTranscription = { [weak self] text in
            DispatchQueue.main.async {
                self?.receivedTranscriptCount += 1
                self?.updateDebugInfo()
                self?.appendHistory("Baby: \(text)")
            }
        }
        client.onOutputTranscription = { [weak self] text in
            DispatchQueue.main.async {
                self?.receivedTranscriptCount += 1
                self?.updateDebugInfo()
                self?.appendHistory("AI: \(text)")
            }
        }
        client.onTextResponse = { [weak self] text in
            DispatchQueue.main.async {
                self?.appendHistory("💬 \(text)")
            }
        }
        client.onInterrupted = { [weak self] in
            DispatchQueue.main.async {
                self?.stopPlayback()
            }
        }
        client.onError = { [weak self] message in
            DispatchQueue.main.async {
                self?.status = .error
                self?.errorMessage = message
                self?.isSessionActive = false
                self?.isSessionReady = false
            }
        }
        client.onClosed = { [weak self] reason in
            DispatchQueue.main.async {
                if let reason = reason {
                    self?.errorMessage = "Socket closed: \(reason)"
                } else {
                    self?.errorMessage = "Socket closed."
                }
                self?.status = .error
                self?.isSessionActive = false
                self?.isSessionReady = false
            }
        }
        client.onConnected = { [weak self] in
            DispatchQueue.main.async {
                self?.updateDebugInfo()
            }
        }
        client.onSetupComplete = { [weak self] in
            DispatchQueue.main.async {
                self?.status = .active
                self?.isSessionReady = true
                self?.appendHistory("Session ready. Listening...")
                self?.updateDebugInfo()
            }
        }

        geminiClient = client
        isSessionActive = true
        status = .listening
        client.connect()
    }

    private func sendAudioToGemini(buffer: AVAudioPCMBuffer) {
        guard isSessionReady else { return }
        guard let converter = inputConverter, let targetInputFormat = targetInputFormat else { return }

        sendGateCounter += 1
        if sendGateCounter % sendStride != 0 {
            return
        }

        let inputRate = inputFormat?.sampleRate ?? 16000
        let ratio = targetInputFormat.sampleRate / inputRate
        let targetFrameCapacity = AVAudioFrameCount(Double(buffer.frameLength) * ratio)
        guard let convertedBuffer = AVAudioPCMBuffer(pcmFormat: targetInputFormat, frameCapacity: targetFrameCapacity) else { return }

        var error: NSError?
        let inputBlock: AVAudioConverterInputBlock = { _, outStatus in
            outStatus.pointee = .haveData
            return buffer
        }

        converter.convert(to: convertedBuffer, error: &error, withInputFrom: inputBlock)
        if error != nil { return }

        guard let pcmData = AudioPCMConverter.int16Data(from: convertedBuffer) else { return }
        let mimeType = "audio/pcm;rate=16000"
        let base64 = pcmData.base64EncodedString()
        geminiClient?.sendAudio(base64Data: base64, mimeType: mimeType)
        DispatchQueue.main.async {
            self.sentFrameCount += 1
            self.updateDebugInfo()
        }
    }

    private func stopPlayback() {
        if playerNode.isPlaying {
            playerNode.stop()
        }
    }

    private func playAudio(base64: String, mimeType: String) {
        guard let data = Data(base64Encoded: base64) else { return }
        guard let format = outputFormat else { return }

        let sampleCount = data.count / MemoryLayout<Int16>.size
        guard sampleCount > 0 else { return }

        let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(sampleCount))
        buffer?.frameLength = AVAudioFrameCount(sampleCount)

        guard let channel = buffer?.floatChannelData?[0] else { return }
        data.withUnsafeBytes { rawBuffer in
            let int16Buffer = rawBuffer.bindMemory(to: Int16.self)
            for i in 0..<sampleCount {
                let sample = Float(int16Buffer[i]) / 32768.0
                channel[i] = sample
            }
        }

        if !playerNode.isPlaying {
            playerNode.play()
        }
        if let buffer = buffer {
            playerNode.scheduleBuffer(buffer, completionHandler: nil)
        }
    }

    private func updateDebugInfo() {
        debugInfo = "sent:\(sentFrameCount) recv_audio:\(receivedAudioCount) recv_text:\(receivedTranscriptCount)"
    }

    private func copyBuffer(_ buffer: AVAudioPCMBuffer) -> AVAudioPCMBuffer? {
        let format = buffer.format
        guard let copied = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: buffer.frameCapacity) else { return nil }
        copied.frameLength = buffer.frameLength
        guard let src = buffer.floatChannelData, let dst = copied.floatChannelData else { return nil }
        let channels = Int(format.channelCount)
        let frames = Int(buffer.frameLength)
        let byteCount = frames * MemoryLayout<Float>.size
        for channel in 0..<channels {
            memcpy(dst[channel], src[channel], byteCount)
        }
        return copied
    }
}

struct CryMonitorView: View {
    @StateObject private var viewModel = CryMonitorViewModel()

    private func statusColor() -> Color {
        switch viewModel.status {
        case .idle:
            return Color.gray.opacity(0.2)
        case .listening:
            return Color.yellow.opacity(0.25)
        case .active:
            return Color.green.opacity(0.25)
        case .error:
            return Color.red.opacity(0.2)
        }
    }

    private func statusTextColor() -> Color {
        switch viewModel.status {
        case .idle:
            return .gray
        case .listening:
            return .yellow
        case .active:
            return .green
        case .error:
            return .red
        }
    }

    var body: some View {
        NavigationView {
            ScrollView {
                VStack(spacing: 24) {
                    VStack(spacing: 8) {
                        Text("No More Cry")
                            .font(.system(size: 32, weight: .bold, design: .rounded))
                            .foregroundColor(.appBlue)
                        Text("AI Soothing Companion")
                            .font(.caption)
                            .foregroundColor(.softGray)
                    }

                    VStack(spacing: 18) {
                        Text(viewModel.status.rawValue)
                            .font(.caption.weight(.bold))
                            .textCase(.uppercase)
                            .padding(.horizontal, 14)
                            .padding(.vertical, 6)
                            .background(statusColor())
                            .foregroundColor(statusTextColor())
                            .cornerRadius(20)

                        VStack(spacing: 12) {
                            HStack {
                                Text("Threshold")
                                    .font(.caption.weight(.bold))
                                    .foregroundColor(.appBlue)
                                Spacer()
                                Text("\(Int(viewModel.threshold * 100))%")
                                    .font(.caption.monospacedDigit())
                                    .foregroundColor(.softGray)
                            }

                            Slider(value: $viewModel.threshold, in: 0.0...0.5, step: 0.01)
                                .tint(.appBlue)

                            HStack {
                                Text("Input")
                                    .font(.caption.weight(.bold))
                                    .foregroundColor(.softGray)
                                    .frame(width: 50, alignment: .leading)
                                GeometryReader { geo in
                                    ZStack(alignment: .leading) {
                                        RoundedRectangle(cornerRadius: 6)
                                            .fill(Color.white)
                                            .overlay(
                                                RoundedRectangle(cornerRadius: 6)
                                                    .stroke(Color.dividerGray, lineWidth: 1)
                                            )
                                        RoundedRectangle(cornerRadius: 6)
                                            .fill(viewModel.currentVolume > viewModel.threshold ? Color.cryRed : Color.appBlue)
                                            .frame(width: geo.size.width * CGFloat(min(viewModel.currentVolume * 2, 1)))
                                    }
                                }
                                .frame(height: 10)
                            }
                        }
                        .padding(20)
                        .background(Color.softBlue.opacity(0.4))
                        .cornerRadius(18)

                        VStack(spacing: 8) {
                            if viewModel.history.isEmpty {
                                Text(viewModel.status == .idle ? "Source: Microphone" : "Listening...")
                                    .font(.caption)
                                    .foregroundColor(.softGray)
                            } else {
                                ForEach(viewModel.history.indices, id: \.self) { idx in
                                    Text(viewModel.history[idx])
                                        .font(.caption)
                                        .foregroundColor(.appBlue)
                                }
                            }
                        }
                        .frame(maxWidth: .infinity, minHeight: 90)
                        .padding(.vertical, 8)
                        .background(Color.white)
                        .cornerRadius(16)
                        .overlay(
                            RoundedRectangle(cornerRadius: 16)
                                .stroke(Color.dividerGray, lineWidth: 1)
                        )

                        HStack {
                            if viewModel.status == .idle || viewModel.status == .error {
                                Button {
                                    viewModel.startMonitoring()
                                } label: {
                                    Text("Start Monitoring")
                                        .font(.headline)
                                        .foregroundColor(.white)
                                        .padding(.horizontal, 28)
                                        .padding(.vertical, 12)
                                        .background(Color.appBlue)
                                        .cornerRadius(16)
                                }
                            } else {
                                Button {
                                    viewModel.stopMonitoring()
                                } label: {
                                    Text("Stop Session")
                                        .font(.headline)
                                        .foregroundColor(.cryRed)
                                        .padding(.horizontal, 28)
                                        .padding(.vertical, 12)
                                        .background(Color.white)
                                        .overlay(
                                            RoundedRectangle(cornerRadius: 16)
                                                .stroke(Color.cryRed, lineWidth: 2)
                                        )
                                }
                            }
                        }

                        if let error = viewModel.errorMessage {
                            Text(error)
                                .font(.caption)
                                .foregroundColor(.cryRed)
                                .padding(.vertical, 8)
                                .padding(.horizontal, 12)
                                .background(Color.cryRed.opacity(0.1))
                                .cornerRadius(12)
                        }
                        if !viewModel.debugInfo.isEmpty {
                            Text(viewModel.debugInfo)
                                .font(.caption2)
                                .foregroundColor(.softGray)
                        }
                    }
                    .padding(24)
                    .cardStyle()
                    .padding(.horizontal)

                    Text("Tip: Place the device near the baby. Adjust the threshold if it triggers too easily.")
                        .font(.caption2)
                        .foregroundColor(.softGray)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 28)
                }
                .padding(.vertical)
            }
            .background(Color.softBlue.ignoresSafeArea())
            .navigationTitle("Cry Monitor")
        }
    }
}

#Preview {
    CryMonitorView()
}
