import SwiftUI

@MainActor
final class InsightsViewModel: ObservableObject {
    @Published var summary: ContextSummary? = nil
    @Published var isLoading: Bool = false
    @Published var errorMessage: String? = nil

    private let apiClient = APIClient.shared

    func load() async {
        isLoading = true
        errorMessage = nil
        do {
            summary = try await apiClient.getSummary()
            isLoading = false
        } catch {
            isLoading = false
            errorMessage = error.localizedDescription
        }
    }
}

struct AIInsightsView: View {
    @StateObject private var viewModel = InsightsViewModel()

    var body: some View {
        NavigationView {
            ScrollView {
                VStack(spacing: 20) {
                    VStack(alignment: .leading, spacing: 16) {
                        HStack {
                            Image(systemName: "sparkles")
                                .foregroundColor(.appBlue)
                            Text("AI Insights")
                                .font(.titleSerif)
                        }

                        if viewModel.isLoading {
                            ProgressView("Loading summary...")
                        } else if let summary = viewModel.summary {
                            SummaryCountsView(summary: summary)
                            if let belief = summary.aiBeliefState, !belief.isEmpty {
                                Divider()
                                    .background(Color.dividerGray)
                                BeliefStateView(belief: belief)
                            }
                        } else {
                            Text("No summary data yet.")
                                .font(.bodyRounded)
                                .foregroundColor(.secondary)
                        }

                        if let errorMessage = viewModel.errorMessage {
                            Text(errorMessage)
                                .font(.caption)
                                .foregroundColor(.red)
                        }
                    }
                    .padding(24)
                    .cardStyle()
                    .padding(.horizontal)

                    // Pattern Analysis Section
                    VStack(alignment: .leading, spacing: 16) {
                        Text("Pattern Analysis")
                            .font(.sectionTitle)
                            .padding(.horizontal)

                        ForEach(MockInsightsData.patterns) { pattern in
                            PatternCard(pattern: pattern)
                        }
                    }

                    // Recommendations Section
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Recommendations")
                            .font(.sectionTitle)
                            .padding(.horizontal)

                        ForEach(MockInsightsData.recommendations) { recommendation in
                            RecommendationCard(recommendation: recommendation)
                        }
                    }
                    .padding(.vertical)
                }
                .padding(.vertical)
            }
            .background(Color.softBlue.ignoresSafeArea())
            .navigationTitle("AI Insights")
        }
        .task {
            await viewModel.load()
        }
    }
}

private struct SummaryCountsView: View {
    let summary: ContextSummary

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Last 24 Hours")
                .font(.caption.weight(.bold))
                .foregroundColor(.softGray)

            HStack(spacing: 16) {
                InsightBadge(icon: "fork.knife", text: "Feeding \(summary.last24h?.feedingCount ?? 0)", color: .feedingGreen)
                InsightBadge(icon: "drop.fill", text: "Diaper \(summary.last24h?.diaperCount ?? 0)", color: .appBlue)
            }

            HStack(spacing: 16) {
                InsightBadge(icon: "moon.zzz.fill", text: "Sleep \(summary.last24h?.sleepSessions ?? 0)", color: .sleepBlue)
                InsightBadge(icon: "waveform", text: "Crying \(summary.last24h?.cryingEvents ?? 0)", color: .cryRed)
            }
        }
    }
}

private struct BeliefStateView: View {
    let belief: [String: Double]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Belief State")
                .font(.caption.weight(.bold))
                .foregroundColor(.softGray)
            ForEach(belief.keys.sorted(), id: \.self) { key in
                let value = belief[key] ?? 0
                Text("\(key): \(String(format: "%.2f", value))")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        }
    }
}

struct InsightBadge: View {
    let icon: String
    let text: String
    let color: Color

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: icon)
                .font(.system(size: 14))
            Text(text)
                .font(.caption)
        }
        .foregroundColor(color)
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(color.opacity(0.1))
        .cornerRadius(12)
    }
}

private struct PatternCard: View {
    let pattern: PatternItem

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: pattern.icon)
                    .font(.system(size: 24))
                    .foregroundColor(pattern.color)

                VStack(alignment: .leading, spacing: 2) {
                    Text(pattern.title)
                        .font(.headline)
                    Text(pattern.trend)
                        .font(.caption)
                        .foregroundColor(.softGray)
                }
                Spacer()
            }

            Text(pattern.description)
                .font(.bodyRounded)
                .foregroundColor(.secondary)
                .lineSpacing(4)
        }
        .padding(20)
        .cardStyle()
        .padding(.horizontal)
    }
}

private struct RecommendationCard: View {
    let recommendation: RecommendationItem

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: recommendation.icon)
                .font(.system(size: 20))
                .foregroundColor(recommendation.color)

            Text(recommendation.text)
                .font(.bodyRounded)
                .foregroundColor(.primary)
                .lineSpacing(4)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(16)
        .background(Color.alertBg)
        .cornerRadius(16)
        .padding(.horizontal)
    }
}

#Preview {
    AIInsightsView()
}
