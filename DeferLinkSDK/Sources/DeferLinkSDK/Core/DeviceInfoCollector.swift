// DeviceInfoCollector.swift
// DeferLinkSDK

import UIKit

struct DeviceInfoCollector {

    // MARK: - Device Model (hardware identifier, e.g. "iPhone15,2")

    static func model() -> String {
        var info = utsname()
        uname(&info)
        return withUnsafePointer(to: &info.machine) {
            $0.withMemoryRebound(to: CChar.self, capacity: 1) { String(cString: $0) }
        }
    }

    // MARK: - Locale / Language

    static func language() -> String {
        Locale.preferredLanguages.first ?? Locale.current.identifier
    }

    // MARK: - Timezone

    static func timezone() -> String {
        TimeZone.current.identifier
    }

    // MARK: - Screen (physical pixels)

    static func screenSize() -> (width: Int, height: Int) {
        let bounds = UIScreen.main.bounds
        let scale  = UIScreen.main.scale
        return (Int(bounds.width * scale), Int(bounds.height * scale))
    }

    // MARK: - User Agent

    static func userAgent(sdkVersion: String = "1.0") -> String {
        let os  = UIDevice.current.systemVersion
        let mdl = model()
        let app = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0"
        return "DeferLinkSDK/\(sdkVersion) App/\(app) (iOS \(os); \(mdl))"
    }

    // MARK: - IDFV

    static func idfv() -> String? {
        UIDevice.current.identifierForVendor?.uuidString
    }

    // MARK: - App Version

    static func appVersion() -> String {
        Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0"
    }
}
