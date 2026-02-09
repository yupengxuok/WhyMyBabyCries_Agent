import SwiftUI
import AVFoundation

enum MonitorStatus: String {
    case idle = "Ready"
    case listening = "Monitoring..."
    case active = "Engaged"
    case error = "Error"
}

@MainActor
final class CryMonitorViewModel: ObservableObject {
    @Published var status: MonitorStatus = .idle
    @Published var currentVolume: Float = 0
    @Published var threshold: Float = 0.15
    @Published var history: [String] = []
    @Published var errorMessage: String? = nil
    @Published var debugInfo: String = ""

    @Published var partialGuidance: PartialGuidance? = nil
    @Published var finalGuidance: AIGuidance? = nil
    @Published var noticeText: String? = nil
    @Published var guidanceUnavailable: Bool = false
    @Published var finalConfidenceLevel: String? = nil
    @Published var finalUncertaintyNote: String? = nil

    private let audioEngine = AVAudioEngine()
    private var inputFormat: AVAudioFormat?
    private var inputConverter: AVAudioConverter?
    private var targetInputFormat: AVAudioFormat?

    private var isSessionActive = false
    private var isSessionReady = false
    private var streamId: String?
    private var eventId: String?
    private var chunksSent = 0

    private let audioSendQueue = DispatchQueue(label: "babycare.audio.send.queue")
    private let sendStride = 1
    private var sendGateCounter = 0

    private let apiClient = APIClient.shared

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
                self.configureAndStartEngine()
            }
        }
    }

    func stopMonitoring() {
        audioEngine.inputNode.removeTap(onBus: 0)
        audioEngine.stop()
        currentVolume = 0

        if isSessionActive, let streamId = streamId {
            Task {
                await finishLiveSession(streamId: streamId)
            }
        } else {
            resetSessionState()
            status = .idle
        }
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
                self.isSessionActive = true
                self.appendHistory("Cry detected. Starting live stream...")
                Task {
                    await self.startLiveSession()
                }
            }
        }

        if isSessionActive, isSessionReady, let copied = copyBuffer(buffer) {
            audioSendQueue.async { [weak self] in
                self?.sendAudioChunk(buffer: copied)
            }
        }
    }

    private func appendHistory(_ text: String) {
        history.append(text)
        if history.count > 10 {
            history.removeFirst(history.count - 10)
        }
    }

    private func startLiveSession() async {
        let request = LiveStartRequest(
            occurredAt: DateHelpers.isoNow(),
            abVariant: nil,
            audioMimeType: "audio/pcm;rate=16000",
            payload: ["note": "live recording"],
            tags: nil
        )

        do {
            let response = try await apiClient.startLiveCrying(request: request)
            streamId = response.streamId
            eventId = response.eventId
            isSessionReady = true
            status = .active
            appendHistory("Live stream started.")
            updateDebugInfo()
        } catch {
            status = .error
            errorMessage = error.localizedDescription
            isSessionActive = false
            isSessionReady = false
        }
    }

    private func sendAudioChunk(buffer: AVAudioPCMBuffer) {
        guard isSessionReady, let streamId = streamId else { return }
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
        if pcmData.count > 512 * 1024 { return }

        Task {
            do {
                let response = try await apiClient.sendLiveChunk(streamId: streamId, chunk: pcmData, mimeType: "audio/pcm;rate=16000")
                if let partial = response.partialGuidance {
                    partialGuidance = partial
                    updateDebugInfo()
                }
                chunksSent += 1
            } catch {
                self.status = .error
                self.errorMessage = error.localizedDescription
            }
        }
    }

    private func finishLiveSession(streamId: String) async {
        do {
            let response = try await apiClient.finishLiveCrying(streamId: streamId)
            if let event = response.event {
                applyFinalEvent(event)
            }
            appendHistory("Live stream completed.")
        } catch {
            errorMessage = error.localizedDescription
            status = .error
        }

        resetSessionState()
        status = .idle
    }

    private func applyFinalEvent(_ event: APIEvent) {
        if let payload = event.payload {
            noticeText = payload.notice
            if let guidance = payload.aiGuidance {
                finalGuidance = guidance
                guidanceUnavailable = false
                finalConfidenceLevel = guidance.confidenceLevel
                finalUncertaintyNote = guidance.uncertaintyNote
            } else {
                finalGuidance = nil
                guidanceUnavailable = true
                finalConfidenceLevel = nil
                finalUncertaintyNote = nil
            }
        } else {
            noticeText = nil
            finalGuidance = nil
            guidanceUnavailable = true
            finalConfidenceLevel = nil
            finalUncertaintyNote = nil
        }
    }

    private func resetSessionState() {
        isSessionActive = false
        isSessionReady = false
        streamId = nil
        eventId = nil
        sendGateCounter = 0
        chunksSent = 0
        updateDebugInfo()
    }

    private func updateDebugInfo() {
        let idText = eventId ?? "-"
        let streamText = streamId ?? "-"
        debugInfo = "event:\(idText) stream:\(streamText) chunks:\(chunksSent)"
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
                                            .frame(height: 12)
                                        RoundedRectangle(cornerRadius: 6)
                                            .fill(Color.appBlue)
                                            .frame(width: CGFloat(viewModel.currentVolume) * geo.size.width * 8, height: 12)
                                    }
                                }
                                .frame(height: 12)
                            }
                        }
                        .padding(.horizontal)

                        HStack(spacing: 16) {
                            Button(action: viewModel.startMonitoring) {
                                Label("Start", systemImage: "play.fill")
                                    .frame(maxWidth: .infinity)
                            }
                            .buttonStyle(.borderedProminent)

                            Button(action: viewModel.stopMonitoring) {
                                Label("Stop", systemImage: "stop.fill")
                                    .frame(maxWidth: .infinity)
                            }
                            .buttonStyle(.bordered)
                        }
                        .padding(.horizontal)

                        if let error = viewModel.errorMessage {
                            Text(error)
                                .font(.caption)
                                .foregroundColor(.red)
                                .multilineTextAlignment(.center)
                        }
                    }

                    if let notice = viewModel.noticeText {
                        Text(notice)
                            .font(.caption)
                            .foregroundColor(.softGray)
                            .lineLimit(1)
                            .truncationMode(.tail)
                            .padding(.horizontal)
                    }

                    GuidanceSection(title: "Live Guidance", guidance: viewModel.partialGuidance)
                        .padding(.horizontal)

                    VStack(alignment: .leading, spacing: 12) {
                        Text("Final Guidance")
                            .font(.sectionTitle)
                            .foregroundColor(.appBlue)

                        if let guidance = viewModel.finalGuidance {
                            GuidanceDetailView(guidance: guidance)
                        } else if viewModel.guidanceUnavailable {
                            Text("Guidance unavailable.")
                                .font(.bodyRounded)
                                .foregroundColor(.secondary)
                        } else {
                            Text("Awaiting final analysis...")
                                .font(.bodyRounded)
                                .foregroundColor(.secondary)
                        }

                        if let confidence = viewModel.finalConfidenceLevel {
                            Text("Confidence: \(confidence)")
                                .font(.caption)
                                .foregroundColor(.softGray)
                        }

                        if let note = viewModel.finalUncertaintyNote {
                            Text(note)
                                .font(.caption)
                                .foregroundColor(.softGray)
                        }
                    }
                    .padding(20)
                    .cardStyle()
                    .padding(.horizontal)

                    if !viewModel.history.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Session History")
                                .font(.sectionTitle)
                                .foregroundColor(.appBlue)
                            ForEach(viewModel.history.indices, id: \.self) { index in
                                Text(viewModel.history[index])
                                    .font(.caption)
                                    .foregroundColor(.softGray)
                            }
                        }
                        .padding(20)
                        .cardStyle()
                        .padding(.horizontal)
                    }
                }
                .padding(.vertical, 24)
            }
            .background(Color.softBlue.ignoresSafeArea())
            .navigationTitle("Live Monitor")
        }
    }
}

private struct GuidanceSection: View {
    let title: String
    let guidance: PartialGuidance?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(title)
                .font(.sectionTitle)
                .foregroundColor(.appBlue)

            if let guidance = guidance {
                if let cause = guidance.mostLikelyCause?.label {
                    Text("Most likely: \(cause)")
                        .font(.bodyRounded)
                }
                if let action = guidance.recommendedNextAction {
                    Text("Next action: \(action)")
                        .font(.bodyRounded)
                        .foregroundColor(.secondary)
                }
                if let confidence = guidance.confidenceLevel {
                    Text("Confidence: \(confidence)")
                        .font(.caption)
                        .foregroundColor(.softGray)
                }
            } else {
                Text("Listening for partial guidance...")
                    .font(.bodyRounded)
                    .foregroundColor(.secondary)
            }
        }
        .padding(20)
        .cardStyle()
    }
}

private struct GuidanceDetailView: View {
    let guidance: AIGuidance

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let cause = guidance.mostLikelyCause?.label {
                Text("Most likely: \(cause)")
                    .font(.headline)
            }
            if let reasoning = guidance.mostLikelyCause?.reasoning {
                Text(reasoning)
                    .font(.bodyRounded)
                    .foregroundColor(.secondary)
            }
            if let actions = guidance.recommendedActions, !actions.isEmpty {
                Text("Recommended actions")
                    .font(.caption.weight(.bold))
                    .foregroundColor(.softGray)
                ForEach(actions.indices, id: \.self) { index in
                    let action = actions[index]
                    Text("\(action.step ?? index + 1). \(action.action ?? "")")
                        .font(.bodyRounded)
                        .foregroundColor(.primary)
                }
            }
            if let notice = guidance.caregiverNotice {
                Text(notice)
                    .font(.caption)
                    .foregroundColor(.softGray)
            }
        }
    }
}

#Preview {
    CryMonitorView()
}
