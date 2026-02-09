import SwiftUI

struct ActivityHistoryView: View {
    var body: some View {
        NavigationView {
            ScrollView {
                VStack(spacing: 16) {
                    // Date Selector
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

                    // Activity Timeline
                    VStack(spacing: 12) {
                        HistoryActivityCard(
                            icon: "fork.knife",
                            title: "Feeding",
                            time: "2:30 PM",
                            duration: "15 min",
                            notes: "80ml formula",
                            color: .feedingGreen
                        )

                        HistoryActivityCard(
                            icon: "moon.zzz.fill",
                            title: "Sleep",
                            time: "1:00 PM",
                            duration: "1.5 hours",
                            notes: "Deep sleep",
                            color: .sleepBlue
                        )

                        HistoryActivityCard(
                            icon: "drop.fill",
                            title: "Diaper Change",
                            time: "11:30 AM",
                            duration: "5 min",
                            notes: "Wet diaper",
                            color: .appBlue
                        )

                        HistoryActivityCard(
                            icon: "face.smiling",
                            title: "Play Time",
                            time: "10:00 AM",
                            duration: "30 min",
                            notes: "Tummy time",
                            color: .feedingGreen
                        )
                    }
                    .padding(.horizontal)
                }
                .padding(.bottom)
            }
            .background(Color.softBlue.ignoresSafeArea())
            .navigationTitle("History")
        }
    }
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
            // Icon
            Circle()
                .fill(color.opacity(0.2))
                .frame(width: 50, height: 50)
                .overlay(
                    Image(systemName: icon)
                        .font(.system(size: 22))
                        .foregroundColor(color)
                )

            // Content
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Text(title)
                        .font(.headline)
                    Spacer()
                    Text(time)
                        .font(.caption)
                        .foregroundColor(.softGray)
                }

                HStack {
                    Label(duration, systemImage: "clock")
                        .font(.caption)
                        .foregroundColor(.softGray)
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
