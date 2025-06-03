//
//  FingerprintCollector.swift
//  DeferLinkTestApp
//
//  Created by Vladimir Martemianov on 3. 6. 2025..
//

import Foundation
import UIKit

class FingerprintCollector {
    
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
