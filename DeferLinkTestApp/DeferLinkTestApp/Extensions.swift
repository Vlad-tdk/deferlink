//
//  Extensions.swift
//  DeferLinkTestApp
//
//  Created by Vladimir Martemianov on 3. 6. 2025..
//

import Foundation
import SwiftUI

// MARK: - Date Extensions
extension Date {
    func timeAgoDisplay() -> String {
        let now = Date()
        let components = Calendar.current.dateComponents([.second, .minute, .hour, .day], from: self, to: now)
        
        if let days = components.day, days > 0 {
            return "\(days)д назад"
        } else if let hours = components.hour, hours > 0 {
            return "\(hours)ч назад"
        } else if let minutes = components.minute, minutes > 0 {
            return "\(minutes)м назад"
        } else if let seconds = components.second, seconds > 5 {
            return "\(seconds)с назад"
        } else {
            return "Сейчас"
        }
    }
}

// MARK: - Color Extensions
extension Color {
    static let success = Color.green
    static let warning = Color.orange
    static let error = Color.red
    static let info = Color.blue
    
    // Custom app colors
    static let deferLinkPrimary = Color(red: 0.2, green: 0.4, blue: 0.8)
    static let deferLinkSecondary = Color(red: 0.1, green: 0.7, blue: 0.4)
}

// MARK: - String Extensions
extension String {
    func truncated(to length: Int) -> String {
        if self.count > length {
            return String(self.prefix(length)) + "..."
        }
        return self
    }
    
    var isValidURL: Bool {
        guard let url = URL(string: self) else { return false }
        return UIApplication.shared.canOpenURL(url)
    }
}

// MARK: - URL Extensions
extension URL {
    func queryParameters() -> [String: String] {
        guard let components = URLComponents(url: self, resolvingAgainstBaseURL: false),
              let queryItems = components.queryItems else {
            return [:]
        }
        
        var params: [String: String] = [:]
        for item in queryItems {
            params[item.name] = item.value
        }
        return params
    }
}

// MARK: - View Extensions
extension View {
    func cornerRadius(_ radius: CGFloat, corners: UIRectCorner) -> some View {
        clipShape(RoundedCorner(radius: radius, corners: corners))
    }
    
    func placeholder<Content: View>(
        when shouldShow: Bool,
        alignment: Alignment = .leading,
        @ViewBuilder placeholder: () -> Content) -> some View {
            
            ZStack(alignment: alignment) {
                placeholder().opacity(shouldShow ? 1 : 0)
                self
            }
        }
}

// MARK: - Custom Shapes
struct RoundedCorner: Shape {
    var radius: CGFloat = .infinity
    var corners: UIRectCorner = .allCorners
    
    func path(in rect: CGRect) -> Path {
        let path = UIBezierPath(
            roundedRect: rect,
            byRoundingCorners: corners,
            cornerRadii: CGSize(width: radius, height: radius)
        )
        return Path(path.cgPath)
    }
}

// MARK: - Notification Extensions
extension Notification.Name {
    static let deepLinkReceived = Notification.Name("DeepLinkReceived")
    static let networkStatusChanged = Notification.Name("NetworkStatusChanged")
    static let testCompleted = Notification.Name("TestCompleted")
}

// MARK: - UserDefaults Extensions
extension UserDefaults {
    enum Keys {
        static let serverURL = "serverURL"
        static let noiseLevel = "noiseLevel"
        static let lastTestTime = "lastTestTime"
        static let testCount = "testCount"
    }
    
    var serverURL: String {
        get { string(forKey: Keys.serverURL) ?? "http://localhost:8000" }
        set { set(newValue, forKey: Keys.serverURL) }
    }
    
    var noiseLevel: Int {
        get { integer(forKey: Keys.noiseLevel) }
        set { set(newValue, forKey: Keys.noiseLevel) }
    }
    
    var lastTestTime: Date? {
        get { object(forKey: Keys.lastTestTime) as? Date }
        set { set(newValue, forKey: Keys.lastTestTime) }
    }
    
    var testCount: Int {
        get { integer(forKey: Keys.testCount) }
        set { set(newValue, forKey: Keys.testCount) }
    }
}

// MARK: - TestResult Extensions
extension TestResult {
    var statusColor: Color {
        if error != nil {
            return .error
        }
        
        if let response = response {
            if response.success && response.matched {
                return .success
            } else if response.success {
                return .warning
            }
        }
        
        return .error
    }
    
    var statusIcon: String {
        if error != nil {
            return "xmark.circle.fill"
        }
        
        if let response = response {
            if response.success && response.matched {
                return "checkmark.circle.fill"
            } else if response.success {
                return "exclamationmark.triangle.fill"
            }
        }
        
        return "xmark.circle.fill"
    }
    
    var shortDescription: String {
        if let error = error {
            return "Ошибка: \(error.truncated(to: 30))"
        }
        
        if let response = response {
            if response.success && response.matched {
                return "Найдено совпадение"
            } else if response.success {
                return "Нет совпадений"
            } else {
                return "Ошибка API"
            }
        }
        
        return "Неизвестно"
    }
}
