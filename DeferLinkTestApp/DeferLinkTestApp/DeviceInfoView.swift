//
//  DeviceInfoView.swift
//  DeferLinkTestApp
//
//  Created by Vladimir Martemianov on 3. 6. 2025..
//

import SwiftUI

struct DeviceInfoView: View {
    @State private var deviceInfo: [String: Any] = [:]
    @State private var fingerprintData: FingerprintData?
    
    var body: some View {
        NavigationView {
            List {
                Section("Информация об устройстве") {
                    ForEach(Array(deviceInfo.keys.sorted()), id: \.self) { key in
                        HStack {
                            Text(localizedKey(key))
                                .foregroundColor(.primary)
                            Spacer()
                            Text("\(deviceInfo[key] ?? "N/A")")
                                .foregroundColor(.secondary)
                                .multilineTextAlignment(.trailing)
                        }
                    }
                }
                
                if let fingerprint = fingerprintData {
                    Section("Fingerprint для API") {
                        FingerprintRowView(label: "Модель", value: fingerprint.model)
                        FingerprintRowView(label: "Язык", value: fingerprint.language)
                        FingerprintRowView(label: "Часовой пояс", value: fingerprint.timezone)
                        FingerprintRowView(label: "Ширина экрана", value: fingerprint.screenWidth.map(String.init))
                        FingerprintRowView(label: "Высота экрана", value: fingerprint.screenHeight.map(String.init))
                        FingerprintRowView(label: "Платформа", value: fingerprint.platform)
                        FingerprintRowView(label: "Версия приложения", value: fingerprint.appVersion)
                        FingerprintRowView(label: "IDFV", value: fingerprint.idfv)
                        
                        VStack(alignment: .leading, spacing: 8) {
                            Text("User Agent:")
                                .foregroundColor(.primary)
                            Text(fingerprint.userAgent ?? "N/A")
                                .font(.caption)
                                .foregroundColor(.secondary)
                                .textSelection(.enabled)
                        }
                        .padding(.vertical, 4)
                    }
                }
                
                Section("Действия") {
                    Button("Обновить информацию") {
                        loadDeviceInfo()
                    }
                    
                    Button("Скопировать fingerprint JSON") {
                        copyFingerprintToClipboard()
                    }
                    
                    Button("Поделиться отчетом") {
                        shareDeviceReport()
                    }
                }
            }
            .navigationTitle("Информация об устройстве")
            .onAppear {
                loadDeviceInfo()
            }
        }
    }
    
    private func loadDeviceInfo() {
        deviceInfo = DeviceInfo.getDetailedDeviceInfo()
        fingerprintData = FingerprintCollector.collectFingerprint()
    }
    
    private func copyFingerprintToClipboard() {
        guard let fingerprint = fingerprintData else { return }
        
        do {
            let jsonData = try JSONEncoder().encode(fingerprint)
            if let jsonString = String(data: jsonData, encoding: .utf8) {
                UIPasteboard.general.string = jsonString
            }
        } catch {
            print("Ошибка кодирования fingerprint: \(error)")
        }
    }
    
    private func shareDeviceReport() {
        guard let fingerprint = fingerprintData else { return }
        
        var report = "DeferLink Device Report\n\n"
        report += "Device Information:\n"
        
        for (key, value) in deviceInfo.sorted(by: { $0.key < $1.key }) {
            report += "- \(localizedKey(key)): \(value)\n"
        }
        
        report += "\nFingerprint Data:\n"
        report += "- Model: \(fingerprint.model ?? "N/A")\n"
        report += "- Language: \(fingerprint.language ?? "N/A")\n"
        report += "- Timezone: \(fingerprint.timezone ?? "N/A")\n"
        report += "- Screen: \(fingerprint.screenWidth ?? 0)x\(fingerprint.screenHeight ?? 0)\n"
        report += "- Platform: \(fingerprint.platform ?? "N/A")\n"
        report += "- App Version: \(fingerprint.appVersion ?? "N/A")\n"
        report += "- IDFV: \(fingerprint.idfv ?? "N/A")\n"
        report += "- User Agent: \(fingerprint.userAgent ?? "N/A")\n"
        
        let activityController = UIActivityViewController(
            activityItems: [report],
            applicationActivities: nil
        )
        
        if let windowScene = UIApplication.shared.connectedScenes.first as? UIWindowScene,
           let window = windowScene.windows.first {
            window.rootViewController?.present(activityController, animated: true)
        }
    }
    
    private func localizedKey(_ key: String) -> String {
        switch key {
        case "model": return "Модель"
        case "systemName": return "Система"
        case "systemVersion": return "Версия ОС"
        case "language": return "Язык"
        case "timezone": return "Часовой пояс"
        case "userAgent": return "User Agent"
        case "screenWidth": return "Ширина экрана"
        case "screenHeight": return "Высота экрана"
        case "screenBounds": return "Границы экрана"
        case "screenScale": return "Масштаб экрана"
        case "platform": return "Платформа"
        case "appVersion": return "Версия приложения"
        case "idfv": return "IDFV"
        case "deviceName": return "Имя устройства"
        case "localizedModel": return "Локализованная модель"
        default: return key
        }
    }
}

struct FingerprintRowView: View {
    let label: String
    let value: String?
    
    var body: some View {
        HStack {
            Text(label)
                .foregroundColor(.primary)
            Spacer()
            Text(value ?? "N/A")
                .foregroundColor(.secondary)
                .textSelection(.enabled)
        }
    }
}
