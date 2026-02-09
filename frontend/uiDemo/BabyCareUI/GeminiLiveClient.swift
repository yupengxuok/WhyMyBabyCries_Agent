import Foundation

final class GeminiLiveClient: NSObject, URLSessionWebSocketDelegate {
    private let apiKey: String
    private let model: String
    private let systemInstruction: String
    private let voiceName: String
    private var urlSession: URLSession?
    private var webSocket: URLSessionWebSocketTask?
    private var isConnected = false
    private var isSetupComplete = false

    var onAudio: ((String, String) -> Void)?
    var onInputTranscription: ((String) -> Void)?
    var onOutputTranscription: ((String) -> Void)?
    var onTextResponse: ((String) -> Void)?
    var onInterrupted: (() -> Void)?
    var onError: ((String) -> Void)?
    var onConnected: (() -> Void)?
    var onClosed: ((String?) -> Void)?
    var onSetupComplete: (() -> Void)?

    init(apiKey: String, model: String, systemInstruction: String, voiceName: String = "Kore") {
        self.apiKey = apiKey
        self.model = model
        self.systemInstruction = systemInstruction
        self.voiceName = voiceName
        self.urlSession = nil
    }

    func connect() {
        guard webSocket == nil else { return }

        guard let url = URL(string: "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key=\(apiKey)") else {
            onError?("Invalid Gemini Live endpoint.")
            return
        }

        var request = URLRequest(url: url)
        request.setValue(apiKey, forHTTPHeaderField: "x-goog-api-key")

        let session = URLSession(configuration: .default, delegate: self, delegateQueue: nil)
        self.urlSession = session
        let socket = session.webSocketTask(with: request)
        webSocket = socket
        socket.resume()
    }

    func sendAudio(base64Data: String, mimeType: String) {
        guard isSetupComplete else { return }
        let payload: [String: Any] = [
            "realtimeInput": [
                "audio": [
                    "data": base64Data,
                    "mimeType": mimeType
                ]
            ]
        ]
        sendJSON(payload)
    }

    func close() {
        webSocket?.cancel(with: .normalClosure, reason: nil)
        webSocket = nil
        isConnected = false
        isSetupComplete = false
        onClosed?(nil)
    }

    private func sendSetup() {
        let payload: [String: Any] = [
            "setup": [
                "model": model,
                "generationConfig": [
                    "responseModalities": ["AUDIO"],
                    "speechConfig": [
                        "voiceConfig": [
                            "prebuiltVoiceConfig": [
                                "voiceName": voiceName
                            ]
                        ]
                    ]
                ],
                "systemInstruction": [
                    "parts": [
                        ["text": systemInstruction]
                    ]
                ],
                "inputAudioTranscription": [:],
                "outputAudioTranscription": [:]
            ]
        ]
        sendJSON(payload)
    }

    private func sendJSON(_ payload: [String: Any]) {
        guard let socket = webSocket, isConnected else { return }
        do {
            let data = try JSONSerialization.data(withJSONObject: payload, options: [])
            let message = URLSessionWebSocketTask.Message.data(data)
            socket.send(message) { [weak self] error in
                if let error = error {
                    self?.onError?("Send failed: \(error.localizedDescription)")
                }
            }
        } catch {
            onError?("Failed to encode JSON.")
        }
    }

    private func receiveLoop() {
        guard let socket = webSocket else { return }
        socket.receive { [weak self] result in
            guard let self = self else { return }
            switch result {
            case .failure(let error):
                self.onError?("Receive failed: \(error.localizedDescription)")
            case .success(let message):
                self.handleMessage(message)
                self.receiveLoop()
            }
        }
    }

    private func handleMessage(_ message: URLSessionWebSocketTask.Message) {
        let data: Data?
        switch message {
        case .data(let d): data = d
        case .string(let text): data = text.data(using: .utf8)
        @unknown default: data = nil
        }

        guard let data = data else { return }

        do {
            guard let json = try JSONSerialization.jsonObject(with: data, options: []) as? [String: Any] else { return }
            if let setupComplete = (json["setupComplete"] as? Bool) ?? (json["setup_complete"] as? Bool) {
                if setupComplete {
                    isSetupComplete = true
                    onSetupComplete?()
                }
                return
            }
            if let setupCompleteObj = json["setupComplete"] as? [String: Any] ?? json["setup_complete"] as? [String: Any] {
                _ = setupCompleteObj
                isSetupComplete = true
                onSetupComplete?()
                return
            }

            if let serverContent = (json["serverContent"] as? [String: Any]) ?? (json["server_content"] as? [String: Any]) {
                if let interrupted = (serverContent["interrupted"] as? Bool) ?? (serverContent["interrupted"] as? Bool), interrupted {
                    onInterrupted?()
                }

                if let inputTranscription = (serverContent["inputTranscription"] as? [String: Any]) ?? (serverContent["input_transcription"] as? [String: Any]),
                   let text = inputTranscription["text"] as? String {
                    onInputTranscription?(text)
                }

                if let outputTranscription = (serverContent["outputTranscription"] as? [String: Any]) ?? (serverContent["output_transcription"] as? [String: Any]),
                   let text = outputTranscription["text"] as? String {
                    onOutputTranscription?(text)
                }

                if let modelTurn = (serverContent["modelTurn"] as? [String: Any]) ?? (serverContent["model_turn"] as? [String: Any]),
                   let parts = modelTurn["parts"] as? [[String: Any]] {
                    for part in parts {
                        // Extract text responses
                        if let text = part["text"] as? String, !text.isEmpty {
                            onTextResponse?(text)
                        }

                        // Extract audio
                        if let inlineData = (part["inlineData"] as? [String: Any]) ?? (part["inline_data"] as? [String: Any]),
                           let base64 = inlineData["data"] as? String,
                           let mimeType = (inlineData["mimeType"] as? String) ?? (inlineData["mime_type"] as? String) {
                            onAudio?(base64, mimeType)
                        }
                    }
                }
            }
        } catch {
            onError?("Failed to parse server message.")
        }
    }

    // MARK: - URLSessionWebSocketDelegate

    func urlSession(_ session: URLSession, webSocketTask: URLSessionWebSocketTask, didOpenWithProtocol protocol: String?) {
        isConnected = true
        sendSetup()
        receiveLoop()
        onConnected?()
    }

    func urlSession(_ session: URLSession, webSocketTask: URLSessionWebSocketTask, didCloseWith closeCode: URLSessionWebSocketTask.CloseCode, reason: Data?) {
        isConnected = false
        isSetupComplete = false
        let reasonText: String?
        if let reason = reason, let text = String(data: reason, encoding: .utf8) {
            reasonText = text
        } else {
            reasonText = "code=\(closeCode.rawValue)"
        }
        onClosed?(reasonText)
    }
}
