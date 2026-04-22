// DeviceCheckManager.swift
// DeferLinkSDK
//
// Apple DeviceCheck — генерация и кэширование токена устройства.
//
// Требования:
//   Xcode → Target → Signing & Capabilities → + Capability → DeviceCheck
//
// На симуляторе DCDevice.current.isSupported = false → всегда возвращает nil.

import Foundation
import DeviceCheck

final class DeviceCheckManager {

    static let shared = DeviceCheckManager()
    private init() {}

    private let defaults        = UserDefaults.standard
    private let tokenKey        = "com.deferlink.sdk.dc_token"
    private let tokenExpiryKey  = "com.deferlink.sdk.dc_token_expiry"
    private let cacheTTL: TimeInterval = 3600 // 1 час

    // MARK: - Public

    /// Возвращает DeviceCheck токен (base64) или nil на симуляторе / при ошибке.
    /// Результат кэшируется на 1 час.
    func token() async -> String? {
        // 1. Проверяем кэш
        if let cached = cachedToken() {
            DeferLinkLogger.debug("DeviceCheck: cached token")
            return cached
        }

        // 2. Генерируем новый
        guard DCDevice.current.isSupported else {
            DeferLinkLogger.debug("DeviceCheck: not supported (simulator?)")
            return nil
        }

        return await withCheckedContinuation { continuation in
            DCDevice.current.generateToken { [weak self] data, error in
                if let error = error {
                    DeferLinkLogger.warning("DeviceCheck error: \(error.localizedDescription)")
                    continuation.resume(returning: nil)
                    return
                }
                guard let data = data else {
                    continuation.resume(returning: nil)
                    return
                }
                let token = data.base64EncodedString()
                self?.cacheToken(token)
                DeferLinkLogger.debug("DeviceCheck: new token generated")
                continuation.resume(returning: token)
            }
        }
    }

    func clearCache() {
        defaults.removeObject(forKey: tokenKey)
        defaults.removeObject(forKey: tokenExpiryKey)
    }

    // MARK: - Private

    private func cachedToken() -> String? {
        guard
            let token  = defaults.string(forKey: tokenKey),
            let expiry = defaults.object(forKey: tokenExpiryKey) as? Date,
            expiry > Date()
        else { return nil }
        return token
    }

    private func cacheToken(_ token: String) {
        defaults.set(token, forKey: tokenKey)
        defaults.set(Date().addingTimeInterval(cacheTTL), forKey: tokenExpiryKey)
    }
}
