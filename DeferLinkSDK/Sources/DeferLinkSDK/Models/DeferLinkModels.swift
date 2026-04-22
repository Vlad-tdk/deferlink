// DeferLinkModels.swift
// DeferLinkSDK
//
// Все публичные модели данных SDK.

import Foundation

// MARK: - Resolution Result

/// Результат разрешения deferred deep link.
public struct DeferLinkResult {

    /// Сессия успешно найдена и сматчена.
    public let matched: Bool

    /// ID промо-акции / кампании из параметра promo_id на сервере.
    public let promoId: String?

    /// Домен из параметра domain.
    public let domain: String?

    /// ID сессии на сервере.
    public let sessionId: String?

    /// URL для редиректа внутри приложения (из app_scheme).
    public let appURL: String?

    /// Метод матчинга: clipboard | safari_cookie | device_check | fingerprint
    public let matchMethod: MatchMethod?

    /// Сырое сообщение от сервера.
    public let message: String?

    public enum MatchMethod: String {
        case clipboard   = "clipboard"
        case safariCookie = "safari_cookie"
        case deviceCheck  = "device_check"
        case fingerprint  = "fingerprint"
        case unknown
    }
}

// MARK: - Internal network models (Codable)

struct ResolveRequestBody: Encodable {
    let fingerprint: FingerprintPayload
    let appScheme: String?
    let fallbackUrl: String?

    enum CodingKeys: String, CodingKey {
        case fingerprint  = "fingerprint"
        case appScheme    = "app_scheme"
        case fallbackUrl  = "fallback_url"
    }
}

struct FingerprintPayload: Encodable {
    let model: String?
    let language: String?
    let timezone: String?
    let userAgent: String?
    let screenWidth: Int?
    let screenHeight: Int?
    let platform: String?
    let appVersion: String?
    let idfv: String?
    let clipboardToken: String?
    let deviceCheckToken: String?
    let safariCookieSessionId: String?
    let isFirstLaunch: Bool?

    enum CodingKeys: String, CodingKey {
        case model               = "model"
        case language            = "language"
        case timezone            = "timezone"
        case userAgent           = "user_agent"
        case screenWidth         = "screen_width"
        case screenHeight        = "screen_height"
        case platform            = "platform"
        case appVersion          = "app_version"
        case idfv                = "idfv"
        case clipboardToken      = "clipboard_token"
        case deviceCheckToken    = "device_check_token"
        case safariCookieSessionId = "safari_cookie_session_id"
        case isFirstLaunch       = "is_first_launch"
    }
}

struct ResolveResponseBody: Decodable {
    let success: Bool
    let promoId: String?
    let domain: String?
    let sessionId: String?
    let appUrl: String?
    let matched: Bool
    let matchMethod: String?
    let message: String?

    enum CodingKeys: String, CodingKey {
        case success     = "success"
        case promoId     = "promo_id"
        case domain      = "domain"
        case sessionId   = "session_id"
        case appUrl      = "app_url"
        case matched     = "matched"
        case matchMethod = "match_method"
        case message     = "message"
    }

    func toDeferLinkResult() -> DeferLinkResult {
        DeferLinkResult(
            matched: matched,
            promoId: promoId,
            domain: domain,
            sessionId: sessionId,
            appURL: appUrl,
            matchMethod: matchMethod.flatMap { DeferLinkResult.MatchMethod(rawValue: $0) } ?? .unknown,
            message: message
        )
    }
}

// MARK: - Errors

public enum DeferLinkError: LocalizedError {
    case notConfigured
    case networkError(Error)
    case serverError(Int, String?)
    case decodingError(Error)
    case invalidURL

    public var errorDescription: String? {
        switch self {
        case .notConfigured:
            return "DeferLink SDK не настроен. Вызовите DeferLink.configure() в AppDelegate."
        case .networkError(let e):
            return "Ошибка сети: \(e.localizedDescription)"
        case .serverError(let code, let msg):
            return "Ошибка сервера \(code): \(msg ?? "")"
        case .decodingError(let e):
            return "Ошибка декодирования ответа: \(e.localizedDescription)"
        case .invalidURL:
            return "Неверный URL сервера"
        }
    }
}
