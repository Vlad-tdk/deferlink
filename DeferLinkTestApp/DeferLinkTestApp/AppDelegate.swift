//
//  AppDelegate.swift
//  DeferLinkTestApp
//
//  Интеграция DeferLinkSDK — минимальный пример.
//

import UIKit
import DeferLinkSDK   // ← подключаем SDK

@main
class AppDelegate: UIResponder, UIApplicationDelegate {

    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
    ) -> Bool {

        // ── 1. Настройка SDK ──────────────────────────────────────────────────
        // baseURL — адрес вашего DeferLink сервера
        // appURLScheme — URL scheme из Info.plist (URL Types → "defrtest")
        DeferLink.configure(
            baseURL: "http://localhost:8000",
            appURLScheme: "defrtest",
            debugLogging: true
        )

        // ── 2. Resolve при первом запуске ─────────────────────────────────────
        DeferLink.shared.resolveOnFirstLaunch { result in
            guard let result = result else {
                print("DeferLink: совпадение не найдено")
                return
            }

            print("✅ DeferLink resolved!")
            print("   promoId:     \(result.promoId ?? "-")")
            print("   domain:      \(result.domain ?? "-")")
            print("   matchMethod: \(result.matchMethod?.rawValue ?? "-")")

            // Уведомляем UI
            NotificationCenter.default.post(
                name: .deferLinkReceived,
                object: nil,
                userInfo: [
                    "promoId": result.promoId as Any,
                    "domain":  result.domain  as Any,
                    "method":  result.matchMethod?.rawValue as Any
                ]
            )
        }

        return true
    }

    // ── 3. Обработка URL scheme ───────────────────────────────────────────────
    func application(
        _ app: UIApplication,
        open url: URL,
        options: [UIApplication.OpenURLOptionsKey: Any] = [:]
    ) -> Bool {
        return DeferLink.shared.handleOpenURL(url)
    }

    // MARK: - Scene lifecycle
    func application(
        _ application: UIApplication,
        configurationForConnecting connectingSceneSession: UISceneSession,
        options: UIScene.ConnectionOptions
    ) -> UISceneConfiguration {
        UISceneConfiguration(name: "Default Configuration", sessionRole: connectingSceneSession.role)
    }
}
