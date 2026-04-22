//
//  FingerprintData.swift
//  DeferLinkTestApp
//
//  Created by Vladimir Martemianov on 3. 6. 2025..
//

import Foundation

// MARK: - Fingerprint Models
struct FingerprintData: Codable {
    let model: String?
    let language: String?
    let timezone: String?
    let userAgent: String?
    let screenWidth: Int?
    let screenHeight: Int?
    let platform: String?
    let appVersion: String?
    let idfv: String?

    // ── Высокоточные сигналы ──────────────────────────────────────────────────
    /// Токен из буфера обмена (записан escape-страницей при IAB → App Store)
    /// Формат: "deferlink:<session_id>"
    let clipboardToken: String?

    /// Apple DeviceCheck token (base64) — подтверждение подлинности устройства
    let deviceCheckToken: String?

    /// Session ID из cookie, полученный через SFSafariViewController shared cookie jar
    let safariCookieSessionId: String?

    /// Первый запуск приложения — самый важный момент для deferred deep link
    let isFirstLaunch: Bool?

    enum CodingKeys: String, CodingKey {
        case model                = "model"
        case language             = "language"
        case timezone             = "timezone"
        case userAgent            = "user_agent"
        case screenWidth          = "screen_width"
        case screenHeight         = "screen_height"
        case platform             = "platform"
        case appVersion           = "app_version"
        case idfv                 = "idfv"
        case clipboardToken       = "clipboard_token"
        case deviceCheckToken     = "device_check_token"
        case safariCookieSessionId = "safari_cookie_session_id"
        case isFirstLaunch        = "is_first_launch"
    }

    /// Инициализатор для обратной совместимости (без новых полей)
    init(
        model: String?,
        language: String?,
        timezone: String?,
        userAgent: String?,
        screenWidth: Int?,
        screenHeight: Int?,
        platform: String?,
        appVersion: String?,
        idfv: String?,
        clipboardToken: String?        = nil,
        deviceCheckToken: String?      = nil,
        safariCookieSessionId: String? = nil,
        isFirstLaunch: Bool?           = nil
    ) {
        self.model                  = model
        self.language               = language
        self.timezone               = timezone
        self.userAgent              = userAgent
        self.screenWidth            = screenWidth
        self.screenHeight           = screenHeight
        self.platform               = platform
        self.appVersion             = appVersion
        self.idfv                   = idfv
        self.clipboardToken         = clipboardToken
        self.deviceCheckToken       = deviceCheckToken
        self.safariCookieSessionId  = safariCookieSessionId
        self.isFirstLaunch          = isFirstLaunch
    }
}

// MARK: - Request/Response Models
struct ResolveRequest: Codable {
    let fingerprint: FingerprintData
    let appScheme: String?
    let fallbackUrl: String?
    
    enum CodingKeys: String, CodingKey {
        case fingerprint = "fingerprint"
        case appScheme = "app_scheme"
        case fallbackUrl = "fallback_url"
    }
}

struct ResolveResponse: Codable {
    let success: Bool
    let promoId: String?
    let domain: String?
    let sessionId: String?
    let redirectUrl: String?
    let appUrl: String?
    let matched: Bool
    let message: String?
    /// Метод матчинга: "clipboard" | "safari_cookie" | "device_check" | "fingerprint"
    let matchMethod: String?

    enum CodingKeys: String, CodingKey {
        case success      = "success"
        case promoId      = "promo_id"
        case domain       = "domain"
        case sessionId    = "session_id"
        case redirectUrl  = "redirect_url"
        case appUrl       = "app_url"
        case matched      = "matched"
        case message      = "message"
        case matchMethod  = "match_method"
    }
}

// MARK: - Test Result Model
struct TestResult {
    let timestamp: Date
    let fingerprint: FingerprintData
    let response: ResolveResponse?
    let error: String?
    let duration: TimeInterval
    
    var isSuccess: Bool {
        return response?.success == true
    }
    
    var statusDescription: String {
        if let error = error {
            return "❌ Ошибка: \(error)"
        }
        
        if let response = response {
            if response.success && response.matched {
                return "✅ Совпадение найдено"
            } else if response.success && !response.matched {
                return "⚠️ Нет совпадений"
            } else {
                return "❌ Ошибка: \(response.message ?? "Неизвестная ошибка")"
            }
        }
        
        return "❓ Неизвестный статус"
    }
}
