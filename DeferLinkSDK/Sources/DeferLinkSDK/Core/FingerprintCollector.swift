// FingerprintCollector.swift
// DeferLinkSDK
//
// Сборка полного fingerprint — объединяет данные устройства,
// clipboard-токен и DeviceCheck в единую структуру для /resolve.

import UIKit

final class FingerprintCollector {

    private let config: DeferLinkConfiguration

    // UserDefaults keys
    private let firstLaunchKey = "com.deferlink.sdk.first_launch_done"

    init(config: DeferLinkConfiguration) {
        self.config = config
    }

    // MARK: - First Launch

    var isFirstLaunch: Bool {
        !UserDefaults.standard.bool(forKey: firstLaunchKey)
    }

    func markFirstLaunchDone() {
        UserDefaults.standard.set(true, forKey: firstLaunchKey)
    }

    // MARK: - Clipboard Token

    /// Прочитать и разобрать clipboard-токен.
    /// Формат: "<prefix>:<session_id>"
    /// После чтения буфер очищается (privacy).
    func readClipboardToken() -> String? {
        let prefix = config.clipboardTokenPrefix + ":"
        guard
            let raw = UIPasteboard.general.string,
            raw.hasPrefix(prefix)
        else { return nil }

        let token = String(raw.dropFirst(prefix.count))
            .trimmingCharacters(in: .whitespacesAndNewlines)

        guard token.count >= 32 else { return nil }

        DeferLinkLogger.debug("Clipboard token found: \(token.prefix(8))...")
        UIPasteboard.general.string = ""  // очищаем после прочтения
        return token
    }

    // MARK: - Full Fingerprint

    /// Собрать полный fingerprint асинхронно.
    /// При первом запуске читает clipboard + запрашивает DeviceCheck токен.
    func collect(safariCookieSessionId: String? = nil) async -> FingerprintPayload {
        let screen = DeviceInfoCollector.screenSize()

        // Clipboard — только на первом запуске
        let clipboardToken: String? = isFirstLaunch ? readClipboardToken() : nil

        // DeviceCheck — кэшируется на 1 час
        let dcToken: String? = await DeviceCheckManager.shared.token()

        if clipboardToken != nil { DeferLinkLogger.debug("Fingerprint includes clipboard token") }
        if dcToken        != nil { DeferLinkLogger.debug("Fingerprint includes DeviceCheck token") }

        return FingerprintPayload(
            model:                 DeviceInfoCollector.model(),
            language:              DeviceInfoCollector.language(),
            timezone:              DeviceInfoCollector.timezone(),
            userAgent:             DeviceInfoCollector.userAgent(),
            screenWidth:           screen.width,
            screenHeight:          screen.height,
            platform:              "iOS",
            appVersion:            DeviceInfoCollector.appVersion(),
            idfv:                  DeviceInfoCollector.idfv(),
            clipboardToken:        clipboardToken,
            deviceCheckToken:      dcToken,
            safariCookieSessionId: safariCookieSessionId,
            isFirstLaunch:         isFirstLaunch
        )
    }
}
