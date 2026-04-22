//
//  FingerprintCollector.swift
//  DeferLinkTestApp
//
//  Created by Vladimir Martemianov on 3. 6. 2025..
//

import Foundation
import UIKit

class FingerprintCollector {

    // MARK: - Clipboard Token Prefix (должен совпадать с бэкендом)
    private static let clipboardPrefix = "deferlink:"

    // MARK: - First Launch Flag
    private static let firstLaunchKey = "com.deferlink.first_launch_done"

    static var isFirstLaunch: Bool {
        return !UserDefaults.standard.bool(forKey: firstLaunchKey)
    }

    static func markFirstLaunchDone() {
        UserDefaults.standard.set(true, forKey: firstLaunchKey)
    }

    // MARK: - Clipboard Reading

    /// Прочитать токен DeferLink из буфера обмена.
    /// Escape-страница записала строку вида "deferlink:<session_id>".
    static func readClipboardToken() -> String? {
        guard let content = UIPasteboard.general.string,
              content.hasPrefix(clipboardPrefix) else {
            return nil
        }

        let token = String(content.dropFirst(clipboardPrefix.count))
            .trimmingCharacters(in: .whitespacesAndNewlines)

        // Базовая валидация — должен выглядеть как UUID
        guard token.count >= 32 else { return nil }

        print("📋 Clipboard token найден: \(token.prefix(8))...")

        // Очищаем буфер обмена после прочтения (privacy best practice)
        UIPasteboard.general.string = ""

        return token
    }

    // MARK: - Base Fingerprint

    static func collectFingerprint() -> FingerprintData {
        let screenSize = DeviceInfo.getScreenSize()

        return FingerprintData(
            model: DeviceInfo.getDeviceModel(),
            language: DeviceInfo.getSystemLanguage(),
            timezone: DeviceInfo.getTimezone(),
            userAgent: DeviceInfo.getUserAgent(),
            screenWidth: screenSize.width,
            screenHeight: screenSize.height,
            platform: DeviceInfo.getPlatform(),
            appVersion: DeviceInfo.getAppVersion(),
            idfv: DeviceInfo.getIDFV()
        )
    }

    // MARK: - Full Fingerprint (async, с DeviceCheck + Clipboard)

    /// Собрать полный fingerprint включая clipboard-токен и DeviceCheck.
    /// Используется при первом запуске приложения.
    static func collectFullFingerprint(
        safariCookieSessionId: String? = nil,
        completion: @escaping (FingerprintData) -> Void
    ) {
        let base = collectFingerprint()
        let clipboardToken = isFirstLaunch ? readClipboardToken() : nil
        let firstLaunch = isFirstLaunch

        // Запрашиваем DeviceCheck токен
        DeviceCheckManager.shared.getCachedOrFreshToken { dcToken in
            let fingerprint = FingerprintData(
                model: base.model,
                language: base.language,
                timezone: base.timezone,
                userAgent: base.userAgent,
                screenWidth: base.screenWidth,
                screenHeight: base.screenHeight,
                platform: base.platform,
                appVersion: base.appVersion,
                idfv: base.idfv,
                clipboardToken: clipboardToken,
                deviceCheckToken: dcToken,
                safariCookieSessionId: safariCookieSessionId,
                isFirstLaunch: firstLaunch
            )

            if clipboardToken != nil {
                print("🎯 Clipboard token включён в fingerprint")
            }
            if dcToken != nil {
                print("🔒 DeviceCheck token включён в fingerprint")
            }

            completion(fingerprint)
        }
    }
    
    static func collectFingerprintWithNoise() -> FingerprintData {
        var fingerprint = collectFingerprint()
        
        let noiseLevel = UserDefaults.standard.integer(forKey: "NoiseLevel")
        
        switch noiseLevel {
        case 1: // Легкий шум
            // Слегка изменяем user agent
            if let ua = fingerprint.userAgent {
                fingerprint = FingerprintData(
                    model: fingerprint.model,
                    language: fingerprint.language,
                    timezone: fingerprint.timezone,
                    userAgent: ua + " TestNoise/1.0",
                    screenWidth: fingerprint.screenWidth,
                    screenHeight: fingerprint.screenHeight,
                    platform: fingerprint.platform,
                    appVersion: fingerprint.appVersion,
                    idfv: fingerprint.idfv
                )
            }
            
        case 2: // Средний шум
            // Изменяем язык
            fingerprint = FingerprintData(
                model: fingerprint.model,
                language: "en_US", // Принудительно английский
                timezone: fingerprint.timezone,
                userAgent: fingerprint.userAgent,
                screenWidth: fingerprint.screenWidth,
                screenHeight: fingerprint.screenHeight,
                platform: fingerprint.platform,
                appVersion: fingerprint.appVersion,
                idfv: fingerprint.idfv
            )
            
        case 3: // Сильный шум
            // Изменяем несколько параметров
            fingerprint = FingerprintData(
                model: "iPhone13,2", // Фиксированная модель
                language: "en_US",
                timezone: "America/New_York", // Другая временная зона
                userAgent: fingerprint.userAgent,
                screenWidth: fingerprint.screenWidth,
                screenHeight: fingerprint.screenHeight,
                platform: fingerprint.platform,
                appVersion: fingerprint.appVersion,
                idfv: fingerprint.idfv
            )
            
        default: // Без шума
            break
        }
        
        return fingerprint
    }
    
    // MARK: - Fingerprint Variations for Testing
    static func createTestVariations() -> [FingerprintData] {
        let base = collectFingerprint()
        var variations: [FingerprintData] = []
        
        // Оригинальный
        variations.append(base)
        
        // Вариация с измененным user agent
        variations.append(FingerprintData(
            model: base.model,
            language: base.language,
            timezone: base.timezone,
            userAgent: (base.userAgent ?? "") + " Modified",
            screenWidth: base.screenWidth,
            screenHeight: base.screenHeight,
            platform: base.platform,
            appVersion: base.appVersion,
            idfv: base.idfv
        ))
        
        // Вариация с измененным размером экрана (системные элементы)
        variations.append(FingerprintData(
            model: base.model,
            language: base.language,
            timezone: base.timezone,
            userAgent: base.userAgent,
            screenWidth: (base.screenWidth ?? 0) - 50, // Учет системных элементов
            screenHeight: (base.screenHeight ?? 0) - 100,
            platform: base.platform,
            appVersion: base.appVersion,
            idfv: base.idfv
        ))
        
        // Вариация с другим языком
        variations.append(FingerprintData(
            model: base.model,
            language: "en_US",
            timezone: base.timezone,
            userAgent: base.userAgent,
            screenWidth: base.screenWidth,
            screenHeight: base.screenHeight,
            platform: base.platform,
            appVersion: base.appVersion,
            idfv: base.idfv
        ))
        
        // Полностью другое устройство
        variations.append(FingerprintData(
            model: "iPhone13,3",
            language: "en_US",
            timezone: "America/New_York",
            userAgent: "DifferentApp/1.0 (iOS 16.0; iPhone13,3)",
            screenWidth: 428,
            screenHeight: 926,
            platform: "iOS",
            appVersion: "1.0.0",
            idfv: nil
        ))
        
        return variations
    }
}
