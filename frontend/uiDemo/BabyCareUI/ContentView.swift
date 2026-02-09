import SwiftUI

struct ContentView: View {
    var body: some View {
        TabView {
            CryMonitorView()
                .tabItem {
                    Label("Home", systemImage: "house")
                }
            HomeLiveStatusView()
                .tabItem {
                    Label("Status", systemImage: "waveform.path.ecg")
                }
            ActivityHistoryView()
                .tabItem {
                    Label("History", systemImage: "clock")
                }
            AIInsightsView()
                .tabItem {
                    Label("Insights", systemImage: "sparkles")
                }
        }
        .tint(Color.appBlue)
    }
}

#Preview {
    ContentView()
}
