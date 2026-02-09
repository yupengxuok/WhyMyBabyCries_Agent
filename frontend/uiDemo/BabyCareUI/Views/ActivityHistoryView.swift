import SwiftUI

@MainActor
final class ActivityHistoryViewModel: ObservableObject {
    @Published var items: [HistoryActivityItem] = []
    @Published var isLoading: Bool = false
    @Published var errorMessage: String? = nil

    private let apiClient = APIClient.shared

    func load() async {
        isLoading = true
        errorMessage = nil
        do {
            let events = try await apiClient.getRecentEvents(limit: 50, since: nil)
            items = events.map { event in
                HistoryActivityItem(
                    id: event.id,
                    icon: icon(for: event.category),
                    title: title(for: event.category),
                    time: formattedTime(for: event),
                    duration: nil,
                    notes: notes(for: event),
                    color: color(for: event.category)
                )
            }
            isLoading = false
        } catch {
            isLoading = false
            errorMessage = error.localizedDescription
        }
    }

    private func formattedTime(for event: APIEvent) -> String {
        if let date = DateHelpers.parseISO(event.occurredAt) {
            return DateHelpers.timeString(from: date)
        }
        return "-"
    }

    private func title(for category: String?) -> String {
        switch category {
        case "feeding": return "Feeding"
        case "sleep": return "Sleep"
        case "diaper": return "Diaper Change"
        case "crying": return "Crying"
        case "comfort": return "Comfort"
        default: return "Activity"
        }
    }

    private func icon(for category: String?) -> String {
        switch category {
        case "feeding": return "fork.knife"
        case "sleep": return "moon.zzz.fill"
        case "diaper": return "drop.fill"
        case "crying": return "waveform"
        case "comfort": return "face.smiling"
        default: return "clock"
        }
    }

    private func color(for category: String?) -> Color {
        switch category {
        case "feeding": return .feedingGreen
        case "sleep": return .sleepBlue
        case "diaper": return .appBlue
        case "crying": return .cryRed
        case "comfort": return .feedingGreen
        default: return .appBlue
        }
    }

    private func notes(for event: APIEvent) -> String {
        if event.category == "feeding", let amount = event.payload?.amountMl {
            return "\(Int(amount)) ml"
        }
        if event.category == "crying", let cause = event.payload?.aiGuidance?.mostLikelyCause?.label {
            return "Likely \(cause)"
        }
        if let note = event.payload?.note {
            return note
        }
        return ""
    }
}

struct ActivityHistoryView: View {
    @StateObject private var viewModel = ActivityHistoryViewModel()

    var body: some View {
        NavigationView {
            ScrollView {
                VStack(spacing: 16) {
                    HStack {
                        Text("Today")
                            .font(.sectionTitle)
                        Spacer()
                        Button(action: {}) {
                            Image(systemName: "calendar")
                                .foregroundColor(.appBlue)
                        }
                    }
                    .padding(.horizontal)
                    .padding(.top)

                    if viewModel.isLoading {
                        ProgressView("Loading history...")
                            .padding(.vertical)
                    }

                    if let errorMessage = viewModel.errorMessage {
                        Text(errorMessage)
                            .font(.caption)
                            .foregroundColor(.red)
                            .padding(.horizontal)
                    }

                    VStack(spacing: 12) {
                        ForEach(viewModel.items) { item in
                            HistoryActivityCard(
                                icon: item.icon,
                                title: item.title,
                                time: item.time,
                                duration: item.duration ?? "",
                                notes: item.notes,
                                color: item.color
                            )
                        }
                    }
                    .padding(.horizontal)
                }
                .padding(.bottom)
            }
            .background(Color.softBlue.ignoresSafeArea())
            .navigationTitle("History")
        }
        .task {
            await viewModel.load()
        }
    }
}

struct HistoryActivityItem: Identifiable {
    let id: String
    let icon: String
    let title: String
    let time: String
    let duration: String?
    let notes: String
    let color: Color
}

struct HistoryActivityCard: View {
    let icon: String
    let title: String
    let time: String
    let duration: String
    let notes: String
    let color: Color

    var body: some View {
        HStack(alignment: .top, spacing: 16) {
            Circle()
                .fill(color.opacity(0.2))
                .frame(width: 50, height: 50)
                .overlay(
                    Image(systemName: icon)
                        .font(.system(size: 22))
                        .foregroundColor(color)
                )

            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Text(title)
                        .font(.headline)
                    Spacer()
                    Text(time)
                        .font(.caption)
                        .foregroundColor(.softGray)
                }

                if !duration.isEmpty {
                    HStack {
                        Label(duration, systemImage: "clock")
                            .font(.caption)
                            .foregroundColor(.softGray)
                    }
                }

                if !notes.isEmpty {
                    Text(notes)
                        .font(.bodyRounded)
                        .foregroundColor(.secondary)
                        .lineLimit(2)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(16)
        .cardStyle()
    }
}

#Preview {
    ActivityHistoryView()
}
