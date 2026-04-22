// DeferLink.swift
// DeferLinkSDK
//
// Главная точка входа в SDK.
//
// ─── Минимальная интеграция (3 шага) ───────────────────────────────────────
//
//  // 1. AppDelegate — настройка один раз
//  DeferLink.configure(baseURL: "https://api.myapp.com", appURLScheme: "myapp")
//
//  // 2. AppDelegate / SceneDelegate — вызвать при первом запуске
//  DeferLink.shared.resolveOnFirstLaunch { result in
//      if let promoId = result?.promoId {
//          // показать onboarding / перейти на промо-экран
//      }
//  }
//
//  // 3. SceneDelegate.scene(_:openURLContexts:)
//  DeferLink.shared.handleOpenURL(url)
//
// ───────────────────────────────────────────────────────────────────────────

import UIKit
import SafariServices

@MainActor
public final class DeferLink: NSObject {

    // MARK: - Singleton

    public static let shared = DeferLink()
    private override init() {}

    // MARK: - State

    private var config:               DeferLinkConfiguration?
    private var client:               DeferLinkClient?
    private var fingerprintCollector: FingerprintCollector?
    private var eventTracker:         EventTracker?

    private var safariVC:         SFSafariViewController?
    private var safariContinuation: CheckedContinuation<String?, Never>?

    // MARK: - Configure

    /// Настроить SDK. Вызывать один раз в `application(_:didFinishLaunchingWithOptions:)`.
    public static func configure(
        baseURL: String,
        appURLScheme: String = "deferlink",
        debugLogging: Bool   = false
    ) {
        let cfg = DeferLinkConfiguration(
            baseURL: baseURL,
            appURLScheme: appURLScheme,
            debugLogging: debugLogging
        )
        shared.setup(config: cfg)
    }

    /// Настроить SDK с полной конфигурацией.
    public static func configure(with config: DeferLinkConfiguration) {
        shared.setup(config: config)
    }

    private func setup(config: DeferLinkConfiguration) {
        self.config               = config
        let newClient             = DeferLinkClient(config: config)
        self.client               = newClient
        self.fingerprintCollector = FingerprintCollector(config: config)
        self.eventTracker         = EventTracker(client: newClient, queue: EventQueue())
        DeferLinkLogger.isEnabled = config.debugLogging
        DeferLinkLogger.debug("DeferLink SDK configured — baseURL: \(config.baseURL)")
    }

    // MARK: - Resolve on First Launch

    /// Разрешить deferred deep link при первом запуске приложения.
    ///
    /// Порядок матчинга:
    ///   1. Clipboard token  (100%) — из escape-страницы в Facebook IAB
    ///   2. Safari cookie    (~99%) — через SFSafariViewController shared cookie jar
    ///   3. DeviceCheck      (~97%) — Apple-подтверждённый токен устройства
    ///   4. Fingerprint      (60–90%) — timezone + экран + язык + модель
    ///
    /// - Parameter completion: Вызывается на главном потоке. `nil` если совпадение не найдено.
    public func resolveOnFirstLaunch(completion: @escaping @MainActor (DeferLinkResult?) -> Void) {
        Task { @MainActor in
            let result = await resolve()
            completion(result)
        }
    }

    /// async/await версия.
    public func resolve() async -> DeferLinkResult? {
        guard ensureConfigured() else { return nil }
        guard let collector = fingerprintCollector,
              let client    = client,
              let config    = config else { return nil }

        guard collector.isFirstLaunch else {
            DeferLinkLogger.debug("Not first launch — skipping resolve")
            return nil
        }

        DeferLinkLogger.debug("Starting deferred deep link resolve...")

        // Шаг 1: SFSafariViewController — попытка прочитать Safari cookie (Tier 2)
        let safariSessionId = await trySafariCookieResolve(config: config)
        if safariSessionId != nil {
            DeferLinkLogger.debug("Safari cookie session found")
        }

        // Шаг 2–4: Собираем полный fingerprint (clipboard + DeviceCheck) и отправляем
        let payload = await collector.collect(safariCookieSessionId: safariSessionId)

        do {
            let response = try await client.resolve(payload: payload, appScheme: nil)
            let result   = response.toDeferLinkResult()

            if result.matched {
                DeferLinkLogger.debug(
                    "✅ Resolved! method=\(result.matchMethod?.rawValue ?? "?") promoId=\(result.promoId ?? "-")"
                )
                collector.markFirstLaunchDone()
                // Stamp attribution context into EventTracker for all subsequent events
                eventTracker?.sessionId = response.sessionId
                eventTracker?.promoId   = result.promoId
            } else {
                DeferLinkLogger.debug("No match found")
            }

            return result.matched ? result : nil

        } catch {
            DeferLinkLogger.warning("Resolve error: \(error.localizedDescription)")
            return nil
        }
    }

    // MARK: - URL Handling

    /// Передать URL из `scene(_:openURLContexts:)` или `application(_:open:)`.
    ///
    /// SDK обрабатывает:
    ///   - `<scheme>://resolved?session_id=...` — ответ SFSafariViewController
    ///   - `<scheme>://...` — любые другие deep links (forwarded через NotificationCenter)
    ///
    /// - Returns: `true` если URL обработан SDK.
    @discardableResult
    public func handleOpenURL(_ url: URL) -> Bool {
        guard let scheme = config?.appURLScheme,
              url.scheme == scheme else { return false }

        // SFSafariViewController callback
        if url.host == "resolved" {
            let components = URLComponents(url: url, resolvingAgainstBaseURL: false)
            let sessionId  = components?.queryItems?
                .first(where: { $0.name == "session_id" })?.value
            let valid = sessionId == "none" ? nil : sessionId
            resumeSafariResolve(sessionId: valid)
            return true
        }

        // Прочие deep links — уведомляем подписчиков
        NotificationCenter.default.post(
            name: .deferLinkReceived,
            object: nil,
            userInfo: ["url": url]
        )
        return true
    }

    // MARK: - SFSafariViewController (Tier 2)

    private func trySafariCookieResolve(config: DeferLinkConfiguration) async -> String? {
        guard let url = try? client?.safariResolveURL() else { return nil }

        return await withCheckedContinuation { [weak self] continuation in
            guard let self = self else { continuation.resume(returning: nil); return }
            self.safariContinuation = continuation

            let vc = SFSafariViewController(url: url)
            vc.modalPresentationStyle = .overCurrentContext
            vc.view.isHidden = true   // невидимый — пользователь не замечает
            self.safariVC = vc

            guard let topVC = UIApplication.topViewController() else {
                continuation.resume(returning: nil)
                self.safariContinuation = nil
                return
            }
            topVC.present(vc, animated: false)

            // Таймаут
            Task { @MainActor [weak self] in
                try? await Task.sleep(nanoseconds: UInt64(config.safariResolveTimeout * 1_000_000_000))
                guard self?.safariContinuation != nil else { return }
                DeferLinkLogger.debug("SFSafariViewController: timeout")
                self?.resumeSafariResolve(sessionId: nil)
            }
        }
    }

    private func resumeSafariResolve(sessionId: String?) {
        safariVC?.dismiss(animated: false)
        safariVC = nil
        let continuation = safariContinuation
        safariContinuation = nil
        if let sid = sessionId { DeferLinkLogger.debug("Safari cookie: \(sid.prefix(8))...") }
        continuation?.resume(returning: sessionId)
    }

    // MARK: - Event Tracking

    /// Log a custom event.
    ///
    /// ```swift
    /// DeferLink.shared.logEvent("af_content_view", properties: ["content_id": "article_42"])
    /// ```
    public func logEvent(
        _ eventName: String,
        properties:  [String: Any]? = nil,
        appUserId:   String?        = nil
    ) {
        guard ensureConfigured() else { return }
        var ev = DeferLinkEvent(eventName: eventName, properties: properties, appUserId: appUserId)
        eventTracker?.track(ev)
    }

    /// Log a revenue event (e.g. purchase, subscription).
    ///
    /// ```swift
    /// DeferLink.shared.logEvent(
    ///     "af_purchase",
    ///     revenue: 29.99, currency: "USD",
    ///     properties: [DLEventParam.orderId: "order_789"]
    /// )
    /// ```
    public func logEvent(
        _ eventName: String,
        revenue:     Double,
        currency:    String         = "USD",
        properties:  [String: Any]? = nil,
        appUserId:   String?        = nil
    ) {
        guard ensureConfigured() else { return }
        let ev = DeferLinkEvent(
            eventName:  eventName,
            revenue:    revenue,
            currency:   currency,
            properties: properties,
            appUserId:  appUserId
        )
        eventTracker?.track(ev)
    }

    /// Log a pre-built ``DeferLinkEvent``.
    ///
    /// ```swift
    /// DeferLink.shared.logEvent(.purchase(9.99, currency: "EUR"))
    /// ```
    public func logEvent(_ event: DeferLinkEvent) {
        guard ensureConfigured() else { return }
        eventTracker?.track(event)
    }

    /// Set the current user ID for all future events.
    /// Call this after your authentication flow completes.
    public func setUserId(_ userId: String?) {
        eventTracker?.appUserId = userId
    }

    /// Manually flush all buffered events now (e.g. before process exit in tests).
    public func flushEvents() {
        eventTracker?.flush()
    }

    // MARK: - Utilities

    private func ensureConfigured() -> Bool {
        if config == nil {
            DeferLinkLogger.warning("DeferLink SDK not configured. Call DeferLink.configure() first.")
            return false
        }
        return true
    }
}

// MARK: - Notification

public extension Notification.Name {
    /// Отправляется когда приложение получает deep link через URL scheme.
    static let deferLinkReceived = Notification.Name("DeferLinkReceived")
}

// MARK: - UIApplication helper

private extension UIApplication {
    @MainActor
    static func topViewController(
        base: UIViewController? = UIApplication.shared
            .connectedScenes
            .compactMap({ $0 as? UIWindowScene })
            .first(where: { $0.activationState == .foregroundActive })?
            .windows
            .first(where: { $0.isKeyWindow })?
            .rootViewController
    ) -> UIViewController? {
        if let nav = base as? UINavigationController {
            return topViewController(base: nav.visibleViewController)
        }
        if let tab = base as? UITabBarController {
            return topViewController(base: tab.selectedViewController)
        }
        if let presented = base?.presentedViewController {
            return topViewController(base: presented)
        }
        return base
    }
}
