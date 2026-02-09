import SwiftUI

extension Color {
    static let appBlue = Color(red: 0.17, green: 0.43, blue: 0.76)
    static let softBlue = Color(red: 0.91, green: 0.94, blue: 0.98)
    static let softGray = Color(red: 0.55, green: 0.60, blue: 0.67)
    static let cardShadow = Color.black.opacity(0.08)
    static let dividerGray = Color(red: 0.86, green: 0.89, blue: 0.93)
    static let alertBg = Color(red: 1.0, green: 0.93, blue: 0.88)
    static let alertText = Color(red: 0.72, green: 0.34, blue: 0.26)
    static let feedingGreen = Color(red: 0.42, green: 0.73, blue: 0.33)
    static let sleepBlue = Color(red: 0.36, green: 0.55, blue: 0.87)
    static let cryRed = Color(red: 0.85, green: 0.36, blue: 0.38)
}

extension Font {
    static let titleSerif = Font.system(size: 22, weight: .semibold, design: .rounded)
    static let sectionTitle = Font.system(size: 20, weight: .semibold, design: .rounded)
    static let bodyRounded = Font.system(size: 16, weight: .regular, design: .rounded)
}

struct CardModifier: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(
                RoundedRectangle(cornerRadius: 22)
                    .fill(Color.white)
                    .shadow(color: .cardShadow, radius: 18, x: 0, y: 8)
            )
    }
}

extension View {
    func cardStyle() -> some View {
        modifier(CardModifier())
    }
}
