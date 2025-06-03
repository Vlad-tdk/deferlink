//
//  DeepLinkTestView.swift
//  DeferLinkTestApp
//
//  Created by Vladimir Martemianov on 3. 6. 2025..
//

import SwiftUI

struct DeepLinkTestView: View {
    @EnvironmentObject var deferLinkService: DeferLinkService
    @EnvironmentObject var networkManager: NetworkManager
    
    @State private var promoId = "test2024"
    @State private var domain = "test.com"
    @State private var selectedScenario: TestScenario = .immediateResolve
    @State private var showingAlert = false
    @State private var alertMessage = ""
    
    var body: some View {
        NavigationView {
            ScrollView{
                VStack(spacing: 20) {
                    // Connection Status
                    ConnectionStatusView()
                    
                    // Test Configuration
                    VStack(alignment: .leading, spacing: 10) {
                        Text("Конфигурация теста")
                            .font(.headline)
                        
                        HStack {
                            Text("Promo ID:")
                            TextField("test2024", text: $promoId)
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
                    
                    // Test Scenarios
                    VStack(alignment: .leading, spacing: 10) {
                        Text("Сценарии тестирования")
                            .font(.headline)
                        
                        Picker("Сценарий", selection: $selectedScenario) {
                            ForEach(TestScenario.allCases, id: \.self) { scenario in
                                Text(scenario.rawValue).tag(scenario)
                            }
                        }
                        .pickerStyle(SegmentedPickerStyle())
                        
                        Text(selectedScenario.description)
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    .padding()
                    .background(Color(.systemGray6))
                    .cornerRadius(10)
                    
                    // Action Buttons
                    VStack(spacing: 15) {
                        Button(action: {
                            deferLinkService.runScenarioTest(scenario: selectedScenario)
                        }) {
                            HStack {
                                if deferLinkService.isLoading {
                                    ProgressView()
                                        .scaleEffect(0.8)
                                }
                                Text("Запустить сценарий")
                            }
                            .frame(maxWidth: .infinity)
                            .padding()
                            .background(networkManager.isConnected ? Color.blue : Color.gray)
                            .foregroundColor(.white)
                            .cornerRadius(10)
                        }
                        .disabled(!networkManager.isConnected || deferLinkService.isLoading)
                        
                        HStack(spacing: 10) {
                            Button("Одиночный тест") {
                                deferLinkService.runSingleTest(promoId: promoId, domain: domain)
                            }
                            .frame(maxWidth: .infinity)
                            .padding()
                            .background(Color.green)
                            .foregroundColor(.white)
                            .cornerRadius(8)
                            .disabled(!networkManager.isConnected || deferLinkService.isLoading)
                            
                            Button("Полный тест") {
                                deferLinkService.runFullTest(promoId: promoId, domain: domain)
                            }
                            .frame(maxWidth: .infinity)
                            .padding()
                            .background(Color.orange)
                            .foregroundColor(.white)
                            .cornerRadius(8)
                            .disabled(!networkManager.isConnected || deferLinkService.isLoading)
                            
                            Button("Стресс тест") {
                                deferLinkService.runStressTest(count: 5, promoId: promoId, domain: domain)
                            }
                            .frame(maxWidth: .infinity)
                            .padding()
                            .background(Color.red)
                            .foregroundColor(.white)
                            .cornerRadius(8)
                            .disabled(!networkManager.isConnected || deferLinkService.isLoading)
                        }
                        
                        Button("Очистить результаты") {
                            deferLinkService.clearResults()
                        }
                        .foregroundColor(.red)
                    }
                    
                    // Deep Link Status
                    if let lastDeepLink = deferLinkService.lastDeepLink {
                        VStack(alignment: .leading, spacing: 5) {
                            Text("Последний Deep Link:")
                                .font(.headline)
                            Text(lastDeepLink)
                                .font(.caption)
                                .padding(8)
                                .background(Color(.systemGray5))
                                .cornerRadius(5)
                        }
                        .padding()
                        .background(Color(.systemGreen).opacity(0.1))
                        .cornerRadius(10)
                    }
                    
                    // Test Results
                    TestResultsView()
                    
                    Spacer()
                }
                .padding()
                .navigationTitle("DeferLink Тесты")
                .alert("Информация", isPresented: $showingAlert) {
                    Button("OK") { }
                } message: {
                    Text(alertMessage)
                }
            }
        }
    }
}

struct ConnectionStatusView: View {
    @EnvironmentObject var networkManager: NetworkManager
    
    var body: some View {
        HStack {
            Circle()
                .fill(networkManager.isConnected ? Color.green : Color.red)
                .frame(width: 12, height: 12)
            
            Text(networkManager.isConnected ? "Подключено к серверу" : "Нет подключения")
                .font(.subheadline)
            
            Spacer()
            
            Button("Проверить") {
                networkManager.checkConnection()
            }
            .font(.caption)
        }
        .padding()
        .background(Color(.systemGray6))
        .cornerRadius(8)
    }
}

struct TestResultsView: View {
    @EnvironmentObject var deferLinkService: DeferLinkService
    
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Результаты тестов (\(deferLinkService.testResults.count))")
                    .font(.headline)
                
                Spacer()
                
                if !deferLinkService.testResults.isEmpty {
                    NavigationLink("Подробно") {
                        DetailedResultsView()
                            .environmentObject(deferLinkService)
                    }
                    .font(.caption)
                }
            }
            
            if deferLinkService.testResults.isEmpty {
                Text("Результатов пока нет")
                    .foregroundColor(.secondary)
                    .frame(maxWidth: .infinity)
                    .padding()
            } else {
                LazyVStack(spacing: 8) {
                    ForEach(Array(deferLinkService.testResults.prefix(3).enumerated()), id: \.offset) { index, result in
                        TestResultRowView(result: result)
                    }
                }
                
                // Statistics Summary
                let stats = deferLinkService.getTestStatistics()
                if let successRate = stats["success_rate"] as? Double,
                   let matchRate = stats["match_rate"] as? Double {
                    HStack {
                        VStack {
                            Text("\(String(format: "%.1f", successRate))%")
                                .font(.title2)
                                .bold()
                            Text("Успешность")
                                .font(.caption)
                        }
                        
                        Spacer()
                        
                        VStack {
                            Text("\(String(format: "%.1f", matchRate))%")
                                .font(.title2)
                                .bold()
                            Text("Совпадения")
                                .font(.caption)
                        }
                    }
                    .padding()
                    .background(Color(.systemBlue).opacity(0.1))
                    .cornerRadius(8)
                }
            }
        }
    }
}

struct TestResultRowView: View {
    let result: TestResult
    
    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(result.statusDescription)
                        .font(.subheadline)
                        .bold()
                    
                    Spacer()
                    
                    Text("\(String(format: "%.2f", result.duration))s")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                
                if let response = result.response {
                    Text("Session: \(response.sessionId ?? "N/A")")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .lineLimit(1)
                }
                
                Text(DateFormatter.localizedString(from: result.timestamp, dateStyle: .none, timeStyle: .medium))
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            
            Spacer()
        }
        .padding(.vertical, 8)
        .padding(.horizontal, 12)
        .background(Color(.systemGray6))
        .cornerRadius(8)
    }
}
