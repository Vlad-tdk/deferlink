//
//  DeviceInfo.swift
//  DeferLinkTestApp
//
//  Created by Vladimir Martemianov on 3. 6. 2025..
//

import UIKit
import AdSupport

class DeviceInfo {
    
    static func getDeviceModel() -> String {
        var systemInfo = utsname()
        uname(&systemInfo)
        let machineMirror = Mirror(reflecting: systemInfo.machine)
        let identifier = machineMirror.children.reduce("") { identifier, element in
            guard let value = element.value as? Int8, value != 0 else { return identifier }
            return identifier + String(UnicodeScalar(UInt8(value)))
        }
        return identifier
    }
    
    static func getSystemLanguage() -> String {
        return Locale.preferredLanguages.first ?? Locale.current.identifier
    }
    
    static func getTimezone() -> String {
        return TimeZone.current.identifier
    }
    
    static func getUserAgent() -> String {
        let systemVersion = UIDevice.current.systemVersion
        let deviceModel = getDeviceModel()
        let appVersion = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0"
        
        return "DeferLinkTestApp/\(appVersion) (iOS \(systemVersion); \(deviceModel))"
    }
    
    static func getScreenSize() -> (width: Int, height: Int) {
        let bounds = UIScreen.main.bounds
        let scale = UIScreen.main.scale
        
        let width = Int(bounds.width * scale)
        let height = Int(bounds.height * scale)
        
        return (width: width, height: height)
    }
    
    static func getAppVersion() -> String {
        return Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0.0"
    }
    
    static func getIDFV() -> String? {
        return UIDevice.current.identifierForVendor?.uuidString
    }
    
    static func getPlatform() -> String {
        return "iOS"
    }
    
    // MARK: - Detailed Device Information
    static func getDetailedDeviceInfo() -> [String: Any] {
        let screenSize = getScreenSize()
        
        return [
            "model": getDeviceModel(),
            "systemName": UIDevice.current.systemName,
            "systemVersion": UIDevice.current.systemVersion,
            "language": getSystemLanguage(),
            "timezone": getTimezone(),
            "userAgent": getUserAgent(),
            "screenWidth": screenSize.width,
            "screenHeight": screenSize.height,
            "screenBounds": "\(UIScreen.main.bounds.width)x\(UIScreen.main.bounds.height)",
            "screenScale": UIScreen.main.scale,
            "platform": getPlatform(),
            "appVersion": getAppVersion(),
            "idfv": getIDFV() ?? "N/A",
            "deviceName": UIDevice.current.name,
            "localizedModel": UIDevice.current.localizedModel
        ]
    }
}
