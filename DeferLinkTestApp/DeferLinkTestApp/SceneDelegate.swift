//
//  SceneDelegate.swift
//  DeferLinkTestApp
//

import UIKit
import SwiftUI
import DeferLinkSDK

class SceneDelegate: UIResponder, UIWindowSceneDelegate {

    var window: UIWindow?

    func scene(
        _ scene: UIScene,
        willConnectTo session: UISceneSession,
        options connectionOptions: UIScene.ConnectionOptions
    ) {
        let contentView = ContentView()

        if let windowScene = scene as? UIWindowScene {
            let window = UIWindow(windowScene: windowScene)
            window.rootViewController = UIHostingController(rootView: contentView)
            self.window = window
            window.makeKeyAndVisible()
        }

        // Обработка deep link при холодном запуске через URL
        if let url = connectionOptions.urlContexts.first?.url {
            DeferLink.shared.handleOpenURL(url)
        }
    }

    // Горячий запуск через URL scheme (SFSafariViewController callback)
    func scene(_ scene: UIScene, openURLContexts contexts: Set<UIOpenURLContext>) {
        if let url = contexts.first?.url {
            DeferLink.shared.handleOpenURL(url)
        }
    }
}
