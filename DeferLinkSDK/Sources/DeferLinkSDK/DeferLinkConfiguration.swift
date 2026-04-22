// DeferLinkConfiguration.swift
// DeferLinkSDK
//
// Конфигурация SDK — передаётся один раз при запуске приложения.

import Foundation

/// Конфигурация DeferLink SDK.
public struct DeferLinkConfiguration {

    // MARK: - Required

    /// URL вашего DeferLink сервера. Пример: "https://api.myapp.com"
    public let baseURL: String

    // MARK: - Optional

    /// URL scheme вашего приложения (Info.plist → URL Types).
    /// Используется для SFSafariViewController cookie resolve.
    /// Пример: "myapp"
    public let appURLScheme: String

    /// Префикс clipboard-токена. Должен совпадать с CLIPBOARD_TOKEN_PREFIX на сервере.
    /// По умолчанию: "deferlink"
    public let clipboardTokenPrefix: String

    /// Время ожидания SFSafariViewController cookie resolve (секунды).
    /// По умолчанию: 3.0
    public let safariResolveTimeout: TimeInterval

    /// Время ожидания сетевых запросов (секунды).
    /// По умолчанию: 10.0
    public let networkTimeout: TimeInterval

    /// Включить подробное логирование в консоль.
    /// По умолчанию: false
    public let debugLogging: Bool

    // MARK: - Init

    public init(
        baseURL: String,
        appURLScheme: String          = "deferlink",
        clipboardTokenPrefix: String  = "deferlink",
        safariResolveTimeout: TimeInterval = 3.0,
        networkTimeout: TimeInterval  = 10.0,
        debugLogging: Bool            = false
    ) {
        // Убираем trailing slash
        self.baseURL              = baseURL.hasSuffix("/") ? String(baseURL.dropLast()) : baseURL
        self.appURLScheme         = appURLScheme
        self.clipboardTokenPrefix = clipboardTokenPrefix
        self.safariResolveTimeout = safariResolveTimeout
        self.networkTimeout       = networkTimeout
        self.debugLogging         = debugLogging
    }
}
