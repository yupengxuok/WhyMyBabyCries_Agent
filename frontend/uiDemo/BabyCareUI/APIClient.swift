import Foundation

enum APIError: LocalizedError {
    case invalidURL
    case invalidResponse
    case serverError(String)
    case decodingError

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid API URL."
        case .invalidResponse:
            return "Invalid API response."
        case .serverError(let message):
            return message
        case .decodingError:
            return "Failed to decode API response."
        }
    }
}

struct APIClient {
    static let shared = APIClient()

    private let baseURL: URL
    private let session: URLSession
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder

    init(baseURL: URL = AppConfig.apiBaseURL, session: URLSession = .shared) {
        self.baseURL = baseURL
        self.session = session
        self.decoder = JSONDecoder()
        self.encoder = JSONEncoder()
    }

    func getRecentEvents(limit: Int? = nil, since: String? = nil) async throws -> [APIEvent] {
        var components = URLComponents(url: baseURL.appendingPathComponent("api/events/recent"), resolvingAgainstBaseURL: false)
        var queryItems: [URLQueryItem] = []
        if let limit = limit {
            queryItems.append(URLQueryItem(name: "limit", value: String(limit)))
        }
        if let since = since {
            queryItems.append(URLQueryItem(name: "since", value: since))
        }
        if !queryItems.isEmpty {
            components?.queryItems = queryItems
        }
        guard let url = components?.url else { throw APIError.invalidURL }
        let response: RecentEventsResponse = try await requestJSON(url: url, method: "GET", body: Optional<String>.none)
        if response.ok {
            return response.events ?? []
        }
        throw APIError.serverError(response.error ?? "Failed to load recent events.")
    }

    func getSummary() async throws -> ContextSummary {
        let url = baseURL.appendingPathComponent("api/context/summary")
        let response: SummaryResponse = try await requestJSON(url: url, method: "GET", body: Optional<String>.none)
        if response.ok, let summary = response.summary {
            return summary
        }
        throw APIError.serverError(response.error ?? "Failed to load summary.")
    }

    func getMetrics() async throws -> Metrics {
        let url = baseURL.appendingPathComponent("api/metrics")
        let response: MetricsResponse = try await requestJSON(url: url, method: "GET", body: Optional<String>.none)
        if response.ok, let metrics = response.metrics {
            return metrics
        }
        throw APIError.serverError(response.error ?? "Failed to load metrics.")
    }

    func startLiveCrying(request: LiveStartRequest) async throws -> LiveStartResponse {
        let url = baseURL.appendingPathComponent("api/events/crying/live/start")
        let response: LiveStartResponse = try await requestJSON(url: url, method: "POST", body: request)
        if response.ok {
            return response
        }
        throw APIError.serverError(response.error ?? "Failed to start live crying.")
    }

    func sendLiveChunk(streamId: String, chunk: Data, mimeType: String?) async throws -> LiveChunkResponse {
        let url = baseURL.appendingPathComponent("api/events/crying/live/chunk")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"

        let boundary = "Boundary-\(UUID().uuidString)"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")

        let body = MultipartFormBuilder(boundary: boundary)
            .addField(name: "stream_id", value: streamId)
            .addFileField(name: "chunk", filename: "chunk.pcm", mimeType: mimeType ?? "application/octet-stream", data: chunk)
            .addOptionalField(name: "mime_type", value: mimeType)
            .build()
        request.httpBody = body

        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse, (200...299).contains(httpResponse.statusCode) else {
            throw APIError.invalidResponse
        }

        guard let decoded = try? decoder.decode(LiveChunkResponse.self, from: data) else {
            throw APIError.decodingError
        }

        if decoded.ok {
            return decoded
        }
        throw APIError.serverError(decoded.error ?? "Failed to send audio chunk.")
    }

    func finishLiveCrying(streamId: String) async throws -> LiveFinishResponse {
        let url = baseURL.appendingPathComponent("api/events/crying/live/finish")
        let response: LiveFinishResponse = try await requestJSON(url: url, method: "POST", body: ["stream_id": streamId])
        if response.ok {
            return response
        }
        throw APIError.serverError(response.error ?? "Failed to finish live crying.")
    }

    private func requestJSON<T: Decodable>(url: URL, method: String, body: Encodable?) async throws -> T {
        var request = URLRequest(url: url)
        request.httpMethod = method
        if let body = body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try encoder.encode(AnyEncodable(body))
        }

        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse, (200...299).contains(httpResponse.statusCode) else {
            throw APIError.invalidResponse
        }

        guard let decoded = try? decoder.decode(T.self, from: data) else {
            throw APIError.decodingError
        }

        return decoded
    }
}

struct MultipartFormBuilder {
    let boundary: String
    private var data = Data()

    init(boundary: String) {
        self.boundary = boundary
    }

    func addField(name: String, value: String) -> MultipartFormBuilder {
        var builder = self
        let fieldData = "--\(boundary)\r\n" +
        "Content-Disposition: form-data; name=\"\(name)\"\r\n\r\n" +
        "\(value)\r\n"
        if let fieldBytes = fieldData.data(using: .utf8) {
            builder.data.append(fieldBytes)
        }
        return builder
    }

    func addOptionalField(name: String, value: String?) -> MultipartFormBuilder {
        guard let value = value else { return self }
        return addField(name: name, value: value)
    }

    func addFileField(name: String, filename: String, mimeType: String, data: Data) -> MultipartFormBuilder {
        var builder = self
        let header = "--\(boundary)\r\n" +
        "Content-Disposition: form-data; name=\"\(name)\"; filename=\"\(filename)\"\r\n" +
        "Content-Type: \(mimeType)\r\n\r\n"
        if let headerData = header.data(using: .utf8) {
            builder.data.append(headerData)
        }
        builder.data.append(data)
        if let lineBreak = "\r\n".data(using: .utf8) {
            builder.data.append(lineBreak)
        }
        return builder
    }

    func build() -> Data {
        var finalData = data
        if let closing = "--\(boundary)--\r\n".data(using: .utf8) {
            finalData.append(closing)
        }
        return finalData
    }
}

struct AnyEncodable: Encodable {
    private let encodeClosure: (Encoder) throws -> Void

    init<T: Encodable>(_ wrapped: T) {
        self.encodeClosure = wrapped.encode
    }

    func encode(to encoder: Encoder) throws {
        try encodeClosure(encoder)
    }
}
