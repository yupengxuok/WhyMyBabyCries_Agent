import SwiftUI

struct AIInsightsView: View {
    var body: some View {
        NavigationView {
            ScrollView {
                VStack(spacing: 20) {
                    // AI Summary Card
                    VStack(alignment: .leading, spacing: 16) {
                        HStack {
                            Image(systemName: "sparkles")
                                .foregroundColor(.appBlue)
                            Text("AI Insights")
                                .font(.titleSerif)
                        }

                        Text("Your baby is showing healthy sleep patterns and consistent feeding times.")
                            .font(.bodyRounded)
                            .foregroundColor(.primary)
                            .lineSpacing(4)

                        Divider()
                            .background(Color.dividerGray)

                        HStack(spacing: 16) {
                            InsightBadge(icon: "checkmark.circle.fill", text: "Good Sleep", color: .feedingGreen)
                            InsightBadge(icon: "chart.line.uptrend.xyaxis", text: "Regular Feeding", color: .appBlue)
                        }
                    }
                    .padding(24)
                    .cardStyle()
                    .padding(.horizontal)

                    // Pattern Analysis
                    VStack(alignment: .leading, spacing: 16) {
                        Text("Pattern Analysis")
                            .font(.sectionTitle)
                            .padding(.horizontal)

                        PatternCard(
                            title: "Sleep Schedule",
                            icon: "moon.zzz.fill",
                            description: "Baby typically sleeps for 2-3 hours after 1 PM",
                            trend: "Consistent pattern",
                            color: .sleepBlue
                        )

                        PatternCard(
                            title: "Feeding Times",
                            icon: "fork.knife",
                            description: "Average 3-4 hours between feedings",
                            trend: "Normal frequency",
                            color: .feedingGreen
                        )

                        PatternCard(
                            title: "Active Hours",
                            icon: "figure.walk",
                            description: "Most active between 9 AM - 12 PM",
                            trend: "Morning preference",
                            color: .appBlue
                        )
                    }

                    // Recommendations
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Recommendations")
                            .font(.sectionTitle)
                            .padding(.horizontal)

                        RecommendationCard(
                            icon: "lightbulb.fill",
                            text: "Consider starting bedtime routine around 7 PM for better night sleep",
                            color: .alertText
                        )

                        RecommendationCard(
                            icon: "drop.fill",
                            text: "Hydration levels look good - keep current feeding schedule",
                            color: .appBlue
                        )
                    }
                    .padding(.vertical)
                }
                .padding(.vertical)
            }
            .background(Color.softBlue.ignoresSafeArea())
            .navigationTitle("AI Insights")
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

struct PatternCard: View {
    let title: String
    let icon: String
    let description: String
    let trend: String
    let color: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: icon)
                    .foregroundColor(color)
                    .font(.system(size: 24))

                VStack(alignment: .leading, spacing: 4) {
                    Text(title)
                        .font(.headline)
                    Text(trend)
                        .font(.caption)
                        .foregroundColor(.softGray)
                }

                Spacer()
            }

            Text(description)
                .font(.bodyRounded)
                .foregroundColor(.secondary)
                .lineSpacing(4)
        }
        .padding(20)
        .cardStyle()
        .padding(.horizontal)
    }
}

struct RecommendationCard: View {
    let icon: String
    let text: String
    let color: Color

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: icon)
                .foregroundColor(color)
                .font(.system(size: 20))

            Text(text)
                .font(.bodyRounded)
                .foregroundColor(.primary)
                .lineSpacing(4)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.alertBg)
        .cornerRadius(16)
        .padding(.horizontal)
    }
}

#Preview {
    AIInsightsView()
}
