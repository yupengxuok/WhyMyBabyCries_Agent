import Foundation

struct APIEvent: Codable, Identifiable {
    let id: String
    let type: String?
    let occurredAt: String?
    let source: String?
    let category: String?
    let payload: EventPayload?
    let tags: [String]?
    let createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id
        case type
        case occurredAt = "occurred_at"
        case source
        case category
        case payload
        case tags
        case createdAt = "created_at"
    }
}

struct EventPayload: Codable {
    let audioId: String?
    let audioUrl: String?
    let audioPath: String?
    let audioMimeType: String?
    let audioAnalysis: AudioAnalysis?
    let aiGuidance: AIGuidance?
    let aiMeta: AIMeta?
    let notice: String?
    let streaming: StreamingInfo?
    let userFeedback: UserFeedback?
    let amountMl: Double?
    let note: String?

    enum CodingKeys: String, CodingKey {
        case audioId = "audio_id"
        case audioUrl = "audio_url"
        case audioPath = "audio_path"
        case audioMimeType = "audio_mime_type"
        case audioAnalysis = "audio_analysis"
        case aiGuidance = "ai_guidance"
        case aiMeta = "ai_meta"
        case notice
        case streaming
        case userFeedback = "user_feedback"
        case amountMl = "amount_ml"
        case note
    }
}

struct AudioAnalysis: Codable {
    let transcription: String?
    let inference: [String: Double]?
}

struct AIGuidance: Codable {
    struct Cause: Codable {
        let label: String?
        let confidence: Double?
        let reasoning: String?
    }

    struct Action: Codable {
        let step: Int?
        let action: String?
        let rationale: String?
    }

    let mostLikelyCause: Cause?
    let alternativeCauses: [Cause]?
    let recommendedActions: [Action]?
    let caregiverNotice: String?
    let confidenceLevel: String?
    let uncertaintyNote: String?

    enum CodingKeys: String, CodingKey {
        case mostLikelyCause = "most_likely_cause"
        case alternativeCauses = "alternative_causes"
        case recommendedActions = "recommended_actions"
        case caregiverNotice = "caregiver_notice"
        case confidenceLevel = "confidence_level"
        case uncertaintyNote = "uncertainty_note"
    }
}

struct AIMeta: Codable {
    let modelName: String?
    let latencyMs: Double?
    let requestMode: String?

    enum CodingKeys: String, CodingKey {
        case modelName = "model_name"
        case latencyMs = "latency_ms"
        case requestMode = "request_mode"
    }
}

struct StreamingInfo: Codable {
    let streamId: String?
    let status: String?
    let partialEveryChunks: Int?
    let chunksReceived: Int?
    let lastPartialGuidance: PartialGuidance?
    let partialUpdates: [PartialUpdate]?

    enum CodingKeys: String, CodingKey {
        case streamId = "stream_id"
        case status
        case partialEveryChunks = "partial_every_chunks"
        case chunksReceived = "chunks_received"
        case lastPartialGuidance = "last_partial_guidance"
        case partialUpdates = "partial_updates"
    }
}

struct PartialUpdate: Codable {
    let at: String?
    let chunksReceived: Int?
    let partialGuidance: PartialGuidance?

    enum CodingKeys: String, CodingKey {
        case at
        case chunksReceived = "chunks_received"
        case partialGuidance = "partial_guidance"
    }
}

struct PartialGuidance: Codable {
    let mostLikelyCause: AIGuidance.Cause?
    let recommendedNextAction: String?
    let confidenceLevel: String?

    enum CodingKeys: String, CodingKey {
        case mostLikelyCause = "most_likely_cause"
        case recommendedNextAction = "recommended_next_action"
        case confidenceLevel = "confidence_level"
    }
}

struct UserFeedback: Codable {
    let helpful: Bool?
    let resolvedInMinutes: Double?
    let notes: String?

    enum CodingKeys: String, CodingKey {
        case helpful
        case resolvedInMinutes = "resolved_in_minutes"
        case notes
    }
}

struct ContextSummary: Codable {
    let last24h: Last24hCounts?
    let latestEvents: [APIEvent]?
    let aiBeliefState: [String: JSONValue]?

    enum CodingKeys: String, CodingKey {
        case last24h = "last_24h"
        case latestEvents = "latest_events"
        case aiBeliefState = "ai_belief_state"
    }
}

enum JSONValue: Codable, CustomStringConvertible {
    case string(String)
    case number(Double)
    case bool(Bool)
    case object([String: JSONValue])
    case array([JSONValue])
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(Bool.self) {
            self = .bool(value)
        } else if let value = try? container.decode(Double.self) {
            self = .number(value)
        } else if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode([String: JSONValue].self) {
            self = .object(value)
        } else if let value = try? container.decode([JSONValue].self) {
            self = .array(value)
        } else {
            self = .null
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let value):
            try container.encode(value)
        case .number(let value):
            try container.encode(value)
        case .bool(let value):
            try container.encode(value)
        case .object(let value):
            try container.encode(value)
        case .array(let value):
            try container.encode(value)
        case .null:
            try container.encodeNil()
        }
    }

    var description: String {
        switch self {
        case .string(let value):
            return value
        case .number(let value):
            return String(format: "%.2f", value)
        case .bool(let value):
            return value ? "true" : "false"
        case .object(let value):
            let pairs = value.keys.sorted().map { key in
                "\(key): \(value[key]?.description ?? "null")"
            }
            return "{ " + pairs.joined(separator: ", ") + " }"
        case .array(let value):
            return "[" + value.map { $0.description }.joined(separator: ", ") + "]"
        case .null:
            return "null"
        }
    }
}

struct Last24hCounts: Codable {
    let feedingCount: Int?
    let diaperCount: Int?
    let sleepSessions: Int?
    let cryingEvents: Int?

    enum CodingKeys: String, CodingKey {
        case feedingCount = "feeding_count"
        case diaperCount = "diaper_count"
        case sleepSessions = "sleep_sessions"
        case cryingEvents = "crying_events"
    }
}

struct Metrics: Codable {
    let helpfulRate: Double?
    let medianResolvedMinutes: Double?
    let uplift: MetricsUplift?
    let contextComparison: ContextComparison?
    let abComparison: ABComparison?
    let abUplift: MetricsUplift?
    let totals: MetricsTotals?

    enum CodingKeys: String, CodingKey {
        case helpfulRate = "helpful_rate"
        case medianResolvedMinutes = "median_resolved_minutes"
        case uplift
        case contextComparison = "context_comparison"
        case abComparison = "ab_comparison"
        case abUplift = "ab_uplift"
        case totals
    }
}

struct MetricsUplift: Codable {
    let helpfulRateUplift: Double?
    let medianResolvedMinutesDelta: Double?

    enum CodingKeys: String, CodingKey {
        case helpfulRateUplift = "helpful_rate_uplift"
        case medianResolvedMinutesDelta = "median_resolved_minutes_delta"
    }
}

struct ContextComparison: Codable {
    let withContext: MetricsBucket?
    let noContext: MetricsBucket?
    let limitedContext: MetricsBucket?

    enum CodingKeys: String, CodingKey {
        case withContext = "with_context"
        case noContext = "no_context"
        case limitedContext = "limited_context"
    }
}

struct ABComparison: Codable {
    let treatment: MetricsBucket?
    let control: MetricsBucket?
}

struct MetricsBucket: Codable {
    let samples: Int?
    let helpfulRate: Double?
    let medianResolvedMinutes: Double?

    enum CodingKeys: String, CodingKey {
        case samples
        case helpfulRate = "helpful_rate"
        case medianResolvedMinutes = "median_resolved_minutes"
    }
}

struct MetricsTotals: Codable {
    let cryingEvents: Int?
    let feedbackEvents: Int?

    enum CodingKeys: String, CodingKey {
        case cryingEvents = "crying_events"
        case feedbackEvents = "feedback_events"
    }
}

struct RecentEventsResponse: Codable {
    let ok: Bool
    let events: [APIEvent]?
    let error: String?
}

struct SummaryResponse: Codable {
    let ok: Bool
    let summary: ContextSummary?
    let error: String?
}

struct MetricsResponse: Codable {
    let ok: Bool
    let metrics: Metrics?
    let error: String?
}

struct LiveStartResponse: Codable {
    let ok: Bool
    let streamId: String?
    let eventId: String?
    let status: String?
    let partialEveryChunks: Int?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case ok
        case streamId = "stream_id"
        case eventId = "event_id"
        case status
        case partialEveryChunks = "partial_every_chunks"
        case error
    }
}

struct LiveChunkResponse: Codable {
    let ok: Bool
    let streamId: String?
    let status: String?
    let chunksReceived: Int?
    let nextPartialInChunks: Int?
    let partialGuidance: PartialGuidance?
    let stale: Bool?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case ok
        case streamId = "stream_id"
        case status
        case chunksReceived = "chunks_received"
        case nextPartialInChunks = "next_partial_in_chunks"
        case partialGuidance = "partial_guidance"
        case stale
        case error
    }
}

struct LiveFinishResponse: Codable {
    let ok: Bool
    let streamId: String?
    let event: APIEvent?
    let status: String?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case ok
        case streamId = "stream_id"
        case event
        case status
        case error
    }
}

struct LiveStartRequest: Encodable {
    let occurredAt: String
    let abVariant: String?
    let audioMimeType: String
    let payload: [String: String]?
    let tags: [String]?

    enum CodingKeys: String, CodingKey {
        case occurredAt = "occurred_at"
        case abVariant = "ab_variant"
        case audioMimeType = "audio_mime_type"
        case payload
        case tags
    }
}

struct ManualEventRequest: Encodable {
    let occurredAt: String
    let category: String
    let payload: [String: String]?
    let tags: [String]?

    enum CodingKeys: String, CodingKey {
        case occurredAt = "occurred_at"
        case category
        case payload
        case tags
    }
}

struct ManualEventResponse: Codable {
    let ok: Bool
    let event: APIEvent?
    let error: String?
}
