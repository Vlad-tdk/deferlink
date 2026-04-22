//
//  DeviceCheckManager.swift
//  DeferLinkTestApp
//
//  Apple DeviceCheck — генерация токена устройства
//
//  Что даёт DeviceCheck:
//  - Токен уникален для устройства + Team ID разработчика
//  - Не требует разрешения ATT / IDFA
//  - Верифицируется Apple серверами
//  - Работает только в нативном приложении (НЕ в WKWebView/Safari)
//
//  Требования:
//  - Capability "DeviceCheck" в Xcode → Signing & Capabilities
//  - Устройство (не симулятор) — на симуляторе всегда возвращает nil
//

import Foundation
import DeviceCheck

final class DeviceCheckManager {

    static let shared = DeviceCheckManager()
    private init() {}

    // MARK: - Token Generation

    /// Сгенерировать DeviceCheck токен.
    /// Возвращает base64-encoded строку или nil если недоступно (симулятор / ошибка).
    func generateToken(completion: @escaping (String?) -> Void) {
        guard DCDevice.current.isSupported else {
            // Симулятор или устройство без поддержки
            print("⚠️ DeviceCheck: не поддерживается на этом устройстве/симуляторе")
            completion(nil)
            return
        }

        DCDevice.current.generateToken { data, error in
            if let error = error {
                print("❌ DeviceCheck generateToken error: \(error.localizedDescription)")
                completion(nil)
                return
            }

            guard let tokenData = data else {
                print("❌ DeviceCheck: token data is nil")
                completion(nil)
                return
            }

            let base64Token = tokenData.base64EncodedString()
            print("✅ DeviceCheck token generated (\(base64Token.prefix(16))...)")
            completion(base64Token)
        }
    }

    /// async/await версия для удобства
    func generateToken() async -> String? {
        await withCheckedContinuation { continuation in
            generateToken { token in
                continuation.resume(returning: token)
            }
        }
    }

    // MARK: - Cached Token

    private let cacheKey = "com.deferlink.devicecheck.token"
    private let cacheExpiryKey = "com.deferlink.devicecheck.token_expiry"

    /// Получить токен из кэша или сгенерировать новый.
    /// Токен кэшируется на 1 час (Apple рекомендует не генерировать слишком часто).
    func getCachedOrFreshToken(completion: @escaping (String?) -> Void) {
        let now = Date()

        // Проверяем кэш
        if let cached = UserDefaults.standard.string(forKey: cacheKey),
           let expiry = UserDefaults.standard.object(forKey: cacheExpiryKey) as? Date,
           expiry > now {
            print("📦 DeviceCheck: using cached token")
            completion(cached)
            return
        }

        // Генерируем новый
        generateToken { [weak self] token in
            guard let self = self else { completion(token); return }

            if let token = token {
                UserDefaults.standard.set(token, forKey: self.cacheKey)
                UserDefaults.standard.set(
                    Date().addingTimeInterval(3600), // 1 час
                    forKey: self.cacheExpiryKey
                )
            }
            completion(token)
        }
    }

    func clearCache() {
        UserDefaults.standard.removeObject(forKey: cacheKey)
        UserDefaults.standard.removeObject(forKey: cacheExpiryKey)
    }
}
