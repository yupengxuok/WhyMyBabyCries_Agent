import SwiftUI

// MARK: - Pattern Model
struct PatternItem: Identifiable {
    let id = UUID()
    let title: String
    let icon: String
    let description: String
    let trend: String
    let color: Color
}

// MARK: - Recommendation Model
struct RecommendationItem: Identifiable {
    let id = UUID()
    let icon: String
    let text: String
    let color: Color
}

// MARK: - Mock Insights Data
struct MockInsightsData {
    static let patterns: [PatternItem] = [
        PatternItem(
            title: "Sleep Schedule",
            icon: "moon.zzz.fill",
            description: "Baby typically sleeps for 2-3 hours after 1 PM",
            trend: "Consistent pattern",
            color: .sleepBlue
        ),
        PatternItem(
            title: "Feeding Times",
            icon: "fork.knife",
            description: "Average 3-4 hours between feedings",
            trend: "Regular intervals",
            color: .feedingGreen
        ),
        PatternItem(
            title: "Active Hours",
            icon: "figure.walk",
            description: "Most active between 9 AM - 12 PM",
            trend: "Morning energy",
            color: .appBlue
        )
    ]

    static let recommendations: [RecommendationItem] = [
        RecommendationItem(
            icon: "moon.stars.fill",
            text: "Consider starting bedtime routine around 7 PM based on sleep patterns",
            color: .alertText
        ),
        RecommendationItem(
            icon: "drop.fill",
            text: "Hydration levels look good - keep current feeding schedule",
            color: .alertText
        )
    ]
}
