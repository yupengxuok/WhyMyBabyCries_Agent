import SwiftUI

@MainActor
final class HomeLiveStatusViewModel: ObservableObject {
    @Published var activities: [TimelineActivity] = []
    @Published var isLoading: Bool = false
    @Published var errorMessage: String? = nil

    private let apiClient = APIClient.shared

    func load() async {
        isLoading = true
        errorMessage = nil
        do {
            let events = try await apiClient.getRecentEvents(limit: 10, since: nil)
            var timelineActivities = events.map { event in
                TimelineActivity(
                    assetName: assetName(for: event.category),
                    title: title(for: event.category),
                    time: formattedRelativeTime(for: event)
                )
            }

            // Append mock data to ensure the timeline is always well-populated
            timelineActivities.append(contentsOf: createMockActivities())

            activities = timelineActivities
            isLoading = false
        } catch {
            isLoading = false
            errorMessage = error.localizedDescription
        }
    }

    private func formattedRelativeTime(for event: APIEvent) -> String {
        if let date = DateHelpers.parseISO(event.occurredAt) {
            return DateHelpers.relativeString(from: date)
        }
        return "Just now"
    }

    private func title(for category: String?) -> String {
        switch category {
        case "feeding": return "Feeding"
        case "sleep": return "Sleep"
        case "diaper": return "Diaper"
        case "crying": return "Crying"
        case "comfort": return "Comfort"
        default: return "Activity"
        }
    }

    private func assetName(for category: String?) -> String {
        switch category {
        case "feeding": return "RecentFeeding"
        case "sleep": return "RecentSleeping"
        case "crying": return "RecentCrying"
        default: return "RecentFeeding"
        }
    }

    private func createMockActivities() -> [TimelineActivity] {
        [
            TimelineActivity(assetName: "RecentFeeding", title: "Feeding", time: "5 mins ago"),
            TimelineActivity(assetName: "RecentSleeping", title: "Sleeping", time: "30 mins ago"),
            TimelineActivity(assetName: "RecentCrying", title: "Crying", time: "45 mins ago"),
            TimelineActivity(assetName: "RecentFeeding", title: "Feeding", time: "1 hr ago"),
            TimelineActivity(assetName: "RecentSleeping", title: "Sleeping", time: "2 hrs ago")
        ]
    }
}

struct HomeLiveStatusView: View {
    @StateObject private var viewModel = HomeLiveStatusViewModel()

    var body: some View {
        ZStack {
            HomeBackground()
                .ignoresSafeArea()

            ScrollView {
                VStack(spacing: 22) {
                    HomeTopBar()

                    StatusInsightCard()
                    .padding(.horizontal, 20)

                    RecentActivitySection(activities: viewModel.activities)
                        .padding(.horizontal, 20)

                    Spacer(minLength: 16)
                }
                .padding(.top, 6)
            }
        }
        .task {
            await viewModel.load()
        }
    }
}

private struct HomeTopBar: View {
    var body: some View {
        HStack {
            Image(systemName: "house.fill")
                .foregroundColor(.softGray)
                .font(.title2)

            Spacer()

            Text("Home - Live Status")
                .font(.titleSerif)
                .foregroundColor(.primary)

            Spacer()

            Image(systemName: "gearshape.fill")
                .foregroundColor(.softGray)
                .font(.title2)
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 6)
    }
}

private struct StatusInsightCard: View {
    var body: some View {
        VStack(spacing: 16) {
            BabyIllustration()

            Text("80% Likely hungry")
                .font(.system(size: 28, weight: .bold, design: .rounded))
                .foregroundColor(.primary)

            HStack(spacing: 8) {
                HStack(spacing: 6) {
                    ForEach(0..<3) { _ in
                        Circle()
                            .fill(Color.orange)
                            .frame(width: 10, height: 10)
                    }
                }

                Text("Medium Confidence")
                    .font(.bodyRounded)
                    .foregroundColor(.softGray)
            }

            Divider()
                .background(Color.dividerGray)

            Text("This is an AI-inferred belief, not a confirmed cause.")
                .font(.system(size: 14, weight: .regular, design: .rounded))
                .foregroundColor(.softGray)
                .multilineTextAlignment(.center)
        }
        .padding(22)
        .cardStyle()
    }
}

private struct BabyIllustration: View {
    var body: some View {
        Image("BabyIllustration")
            .resizable()
            .scaledToFit()
            .frame(width: 240, height: 140)
    }
}

private struct RecentActivitySection: View {
    let activities: [TimelineActivity]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Recent Activity")
                .font(.sectionTitle)
                .foregroundColor(.primary)

            Rectangle()
                .fill(Color.dividerGray)
                .frame(height: 1)

            if activities.isEmpty {
                Text("No recent events.")
                    .font(.bodyRounded)
                    .foregroundColor(.softGray)
            } else {
                VStack(spacing: 18) {
                    ForEach(Array(activities.enumerated()), id: \.offset) { index, item in
                        TimelineRow(activity: item, index: index)
                    }
                }
                .overlayPreferenceValue(TimelineDotPreferenceKey.self) { anchors in
                    GeometryReader { proxy in
                        let points = anchors.values.map { proxy[$0] }.sorted { $0.y < $1.y }
                        if let first = points.first, let last = points.last {
                            Path { path in
                                path.move(to: CGPoint(x: first.x, y: first.y))
                                path.addLine(to: CGPoint(x: first.x, y: last.y))
                            }
                            .stroke(Color.dividerGray, lineWidth: 2)
                        }
                    }
                }
            }
        }
    }
}

private struct TimelineRow: View {
    let activity: TimelineActivity
    let index: Int

    var body: some View {
        HStack(alignment: .top, spacing: 14) {
            VStack(spacing: 0) {
                Circle()
                    .fill(Color.dividerGray)
                    .frame(width: 10, height: 10)
                    .padding(.top, 8)
                    .anchorPreference(key: TimelineDotPreferenceKey.self, value: .center) { [index: $0] }
            }
            .frame(width: 12)

            HStack(spacing: 12) {
                TimelineIcon(imageName: activity.assetName)

                HStack(spacing: 6) {
                    Text(activity.title)
                        .font(.system(size: 17, weight: .semibold, design: .rounded))
                        .foregroundColor(.primary)
                    Text(activity.time)
                        .font(.system(size: 15, weight: .regular, design: .rounded))
                        .foregroundColor(.softGray)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct TimelineIcon: View {
    let imageName: String

    var body: some View {
        Image(imageName)
            .resizable()
            .scaledToFit()
            .frame(width: 36, height: 36)
    }
}

private struct TimelineDotPreferenceKey: PreferenceKey {
    static var defaultValue: [Int: Anchor<CGPoint>] = [:]

    static func reduce(value: inout [Int: Anchor<CGPoint>], nextValue: () -> [Int: Anchor<CGPoint>]) {
        value.merge(nextValue(), uniquingKeysWith: { $1 })
    }
}

private struct HomeBackground: View {
    var body: some View {
        ZStack {
            LinearGradient(
                colors: [
                    Color(red: 0.96, green: 0.98, blue: 1.0),
                    Color(red: 0.94, green: 0.97, blue: 1.0)
                ],
                startPoint: .top,
                endPoint: .bottom
            )

            WaveShape(yOffset: 0.62, curve: 0.12)
                .fill(Color(red: 0.89, green: 0.94, blue: 0.98))
                .opacity(0.9)
                .ignoresSafeArea()

            WaveShape(yOffset: 0.78, curve: 0.08)
                .fill(Color(red: 0.98, green: 0.95, blue: 0.92))
                .opacity(0.8)
                .ignoresSafeArea()

            WaveShape(yOffset: 0.86, curve: 0.06)
                .fill(Color(red: 0.90, green: 0.96, blue: 0.98))
                .opacity(0.9)
                .ignoresSafeArea()
        }
    }
}

private struct WaveShape: Shape {
    let yOffset: CGFloat
    let curve: CGFloat

    func path(in rect: CGRect) -> Path {
        var path = Path()
        let startY = rect.height * yOffset
        let controlOffset = rect.height * curve

        path.move(to: CGPoint(x: 0, y: startY))
        path.addCurve(
            to: CGPoint(x: rect.width, y: startY),
            control1: CGPoint(x: rect.width * 0.25, y: startY - controlOffset),
            control2: CGPoint(x: rect.width * 0.75, y: startY + controlOffset)
        )
        path.addLine(to: CGPoint(x: rect.width, y: rect.height))
        path.addLine(to: CGPoint(x: 0, y: rect.height))
        path.closeSubpath()
        return path
    }
}

struct TimelineActivity {
    let assetName: String
    let title: String
    let time: String
}

#Preview {
    HomeLiveStatusView()
}
