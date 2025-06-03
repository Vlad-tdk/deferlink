//
//  SettingsView.swift
//  DeferLinkTestApp
//
//  Created by Vladimir Martemianov on 3. 6. 2025..
//

import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var networkManager: NetworkManager
    @State private var serverURL = "http://localhost:8000"
    @State private var noiseLevel = 0
    @State private var showingURLAlert = false
    
    let noiseLevels = [
        "Без шума",
        "Легкий шум (User-Agent)",
        "Средний шум (Язык)",
        "Сильный шум (Модель + Timezone)"
    ]
    
    var body: some View {
        NavigationView {
            Form {
                Section("Подключение к серверу") {
                    HStack {
                        Text("URL сервера:")
                        Spacer()
                        TextField("http://localhost:8000", text: $serverURL)
                            .textFieldStyle(RoundedBorderTextFieldStyle())
                            .autocapitalization(.none)
                            .disableAutocorrection(true)
                    }
                    
                    Button("Обновить URL") {
                        networkManager.baseURL = serverURL
                        networkManager.checkConnection()
                        showingURLAlert = true
                    }
                    
                    HStack {
                        Text("Статус:")
                        Spacer()
                        HStack {
                            Circle()
                                .fill(networkManager.isConnected ? Color.green : Color.red)
                                .frame(width: 10, height: 10)
                            Text(networkManager.isConnected ? "Подключено" : "Отключено")
                        }
                    }
                    
                    Button("Проверить подключение") {
                        networkManager.checkConnection()
                    }
                }
                
                Section("Настройки тестирования") {
                    Picker("Уровень шума", selection: $noiseLevel) {
                        ForEach(0..<noiseLevels.count, id: \.self) { index in
                            Text(noiseLevels[index]).tag(index)
                        }
                    }
                    .onChange(of: noiseLevel) { newValue in
                        UserDefaults.standard.set(newValue, forKey: "NoiseLevel")
                    }
                    
                    Text("Шум помогает тестировать алгоритм сопоставления с различными fingerprint данными")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                
                Section("Быстрые тесты") {
                    NavigationLink("Открыть браузерную ссылку") {
                        BrowserLinkView()
                            .environmentObject(networkManager)
                    }
                    
                    NavigationLink("Статистика сервера") {
                        ServerStatsView()
                            .environmentObject(networkManager)
                    }
                    
                    NavigationLink("Детальные результаты") {
                        DetailedResultsView()
                    }
                }
                
                Section("Информация") {
                    HStack {
                        Text("Версия приложения:")
                        Spacer()
                        Text(DeviceInfo.getAppVersion())
                            .foregroundColor(.secondary)
                    }
                    
                    HStack {
                        Text("iOS версия:")
                        Spacer()
                        Text(UIDevice.current.systemVersion)
                            .foregroundColor(.secondary)
                    }
                    
                    HStack {
                        Text("Модель устройства:")
                        Spacer()
                        Text(DeviceInfo.getDeviceModel())
                            .foregroundColor(.secondary)
                    }
                }
                
                Section("Действия") {
                    Button("Сбросить настройки") {
                        UserDefaults.standard.removeObject(forKey: "NoiseLevel")
                        noiseLevel = 0
                        serverURL = "http://localhost:8000"
                        networkManager.baseURL = serverURL
                    }
                    .foregroundColor(.red)
                }
            }
            .navigationTitle("Настройки")
            .onAppear {
                serverURL = networkManager.baseURL
                noiseLevel = UserDefaults.standard.integer(forKey: "NoiseLevel")
            }
            .alert("URL обновлен", isPresented: $showingURLAlert) {
                Button("OK") { }
            } message: {
                Text("Сервер URL обновлен до: \(serverURL)")
            }
        }
    }
}

struct BrowserLinkView: View {
    @EnvironmentObject var networkManager: NetworkManager
    @State private var promoId = "browser2024"
    @State private var domain = "test.com"
    @State private var generatedURL = ""
    
    var body: some View {
        VStack(spacing: 20) {
            Text("Генератор браузерных ссылок")
                .font(.title2)
                .bold()
            
            Text("Эта ссылка симулирует переход пользователя из браузера")
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
            
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Text("Promo ID:")
                    TextField("browser2024", text: $promoId)
                        .textFieldStyle(RoundedBorderTextFieldStyle())
                }
                
                HStack {
                    Text("Домен:")
                    TextField("test.com", text: $domain)
                        .textFieldStyle(RoundedBorderTextFieldStyle())
                }
            }
            .padding()
            .background(Color(.systemGray6))
            .cornerRadius(10)
            
            Button("Генерировать ссылку") {
                generateBrowserURL()
            }
            .frame(maxWidth: .infinity)
            .padding()
            .background(Color.blue)
            .foregroundColor(.white)
            .cornerRadius(10)
            
            if !generatedURL.isEmpty {
                VStack(alignment: .leading, spacing: 10) {
                    Text("Сгенерированная ссылка:")
                        .font(.headline)
                    
                    Text(generatedURL)
                        .font(.caption)
                        .padding()
                        .background(Color(.systemGray5))
                        .cornerRadius(8)
                        .textSelection(.enabled)
                    
                    HStack {
                        Button("Копировать") {
                            UIPasteboard.general.string = generatedURL
                        }
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(Color.green)
                        .foregroundColor(.white)
                        .cornerRadius(8)
                        
                        Button("Открыть в Safari") {
                            if let url = URL(string: generatedURL) {
                                UIApplication.shared.open(url)
                            }
                        }
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(Color.orange)
                        .foregroundColor(.white)
                        .cornerRadius(8)
                    }
                }
            }
            
            Spacer()
        }
        .padding()
        .navigationTitle("Браузерная ссылка")
        .navigationBarTitleDisplayMode(.inline)
    }
    
    private func generateBrowserURL() {
        let fingerprint = FingerprintCollector.collectFingerprint()
        
        var components = URLComponents(string: "\(networkManager.baseURL)/dl")!
        components.queryItems = [
            URLQueryItem(name: "promo_id", value: promoId),
            URLQueryItem(name: "domain", value: domain),
            URLQueryItem(name: "timezone", value: fingerprint.timezone),
            URLQueryItem(name: "language", value: fingerprint.language),
            URLQueryItem(name: "screen_size", value: "\(fingerprint.screenWidth ?? 0)x\(fingerprint.screenHeight ?? 0)"),
            URLQueryItem(name: "model", value: fingerprint.model)
        ]
        
        generatedURL = components.url?.absoluteString ?? ""
    }
}
