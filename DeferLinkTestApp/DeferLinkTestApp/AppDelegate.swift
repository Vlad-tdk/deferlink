//
//  AppDelegate.swift
//  DeferLinkTestApp
//
//  Created by Vladimir Martemianov on 3. 6. 2025..
//

import UIKit

@main
class AppDelegate: UIResponder, UIApplicationDelegate {
    
    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        print("DeferLink Test App запущено")
        return true
    }
    
    // MARK: - URL Scheme Handling
    func application(_ app: UIApplication, open url: URL, options: [UIApplication.OpenURLOptionsKey : Any] = [:]) -> Bool {
        print("Получен deep link: \(url)")
        
        // Обработка deep link
        if url.scheme == "defrtest" {
            handleDeepLink(url)
            return true
        }
        
        return false
    }
    
    private func handleDeepLink(_ url: URL) {
        print("Обработка deep link: \(url.absoluteString)")
        
        // Получаем параметры из URL
        let urlComponents = URLComponents(url: url, resolvingAgainstBaseURL: false)
        let queryItems = urlComponents?.queryItems
        
        var params: [String: String] = [:]
        queryItems?.forEach { item in
            params[item.name] = item.value
        }
        
        // Отправляем уведомление о получении deep link
        NotificationCenter.default.post(
            name: NSNotification.Name("DeepLinkReceived"),
            object: nil,
            userInfo: [
                "url": url.absoluteString,
                "params": params
            ]
        )
        
        print("Deep link параметры: \(params)")
    }
    
    // MARK: UISceneSession Lifecycle
    func application(_ application: UIApplication, configurationForConnecting connectingSceneSession: UISceneSession, options: UIScene.ConnectionOptions) -> UISceneConfiguration {
        return UISceneConfiguration(name: "Default Configuration", sessionRole: connectingSceneSession.role)
    }
}
