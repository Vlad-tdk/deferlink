//
//  AdditionalViews.swift
//  DeferLinkTestApp
//
//  Created by Vladimir Martemianov on 3. 6. 2025..
//

import SwiftUI

// MARK: - Server Stats View
struct ServerStatsView: View {
    @EnvironmentObject var networkManager: NetworkManager
    @State private var stats: [String: Any] = [:]
    @State private var isLoading = false
    @State private var errorMessage: String?
    
    var body: some View {
        NavigationView {
            List {
                if isLoading {
                    HStack {
                        ProgressView()
                        Text("Загрузка статистики...")
                    }
                } else if let error = errorMessage {
                    Section("Ошибка") {
                        Text(error)
                            .foregroundColor(.red)
                    }
                } else if !stats.isEmpty {
                    Section("Статистика сервера") {
                        if let totalSessions = stats["total_sessions"] as? Int {
                            StatRowView(label: "Общее количество сессий", value: "\(totalSessions)")
                        }
                        
                        if let activeSessions = stats["active_sessions"] as? Int {
                            StatRowView(label: "Активные сессии", value: "\(activeSessions)")
                        }
                        
                        if let resolvedSessions = stats["resolved_sessions"] as? Int {
                            StatRowView(label: "Разрешенные сессии", value: "\(resolvedSessions)")
                        }
                        
                        if let successRate = stats["success_rate"] as? Double {
                            StatRowView(label: "Процент успеха", value: String(format: "%.2f%%", successRate))
                        }
                        
                        if let sessionsLastHour = stats["sessions_last_hour"] as? Int {
                            StatRowView(label: "Сессии за час", value: "\(sessionsLastHour)")
                        }
                        
                        if let avgConfidence = stats["average_confidence"] as? Double {
                            StatRowView(label: "Средняя уверенность", value: String(format: "%.3f", avgConfidence))
                        }
                        
                        if let timestamp = stats["timestamp"] as? String {
                            StatRowView(label: "Время обновления", value: formatTimestamp(timestamp))
                        }
                    }
                    
                    if let matcherStats = stats["matcher_stats"] as? [String: Any] {
                        Section("Статистика алгоритма") {
                            if let totalRequests = matcherStats["total_requests"] as? Int {
                                StatRowView(label: "Всего запросов", value: "\(totalRequests)")
                            }
                            
                            if let successfulMatches = matcherStats["successful_matches"] as? Int {
                                StatRowView(label: "Успешные совпадения", value: "\(successfulMatches)")
                            }
                            
                            if let failedMatches = matcherStats["failed_matches"] as? Int {
                                StatRowView(label: "Неуспешные совпадения", value: "\(failedMatches)")
                            }
                            
                            if let avgConfidence = matcherStats["average_confidence"] as? Double {
                                StatRowView(label: "Средняя уверенность алгоритма", value: String(format: "%.3f", avgConfidence))
                            }
                        }
                    }
                } else {
                    Section {
                        Text("Нет данных")
                            .foregroundColor(.secondary)
                    }
                }
                
                Section("Действия") {
                    Button("Обновить статистику") {
                        loadStats()
                    }
                    .disabled(isLoading || !networkManager.isConnected)
                }
            }
            .navigationTitle("Статистика сервера")
            .onAppear {
                loadStats()
            }
        }
    }
    
    private func loadStats() {
        isLoading = true
        errorMessage = nil
        
        networkManager.getStats { result in
            DispatchQueue.main.async {
                isLoading = false
                
                switch result {
                case .success(let data):
                    stats = data
                case .failure(let error):
                    errorMessage = error.localizedDescription
                }
            }
        }
    }
    
    private func formatTimestamp(_ timestamp: String) -> String {
        let formatter = ISO8601DateFormatter()
        if let date = formatter.date(from: timestamp) {
            let displayFormatter = DateFormatter()
            displayFormatter.dateStyle = .short
            displayFormatter.timeStyle = .medium
            return displayFormatter.string(from: date)
        }
        return timestamp
    }
}

// MARK: - Stat Row View
struct StatRowView: View {
    let label: String
    let value: String
    
    var body: some View {
        HStack {
            Text(label)
                .foregroundColor(.primary)
            Spacer()
            Text(value)
                .foregroundColor(.secondary)
                .bold()
        }
    }
}

// MARK: - Detailed Results View
struct DetailedResultsView: View {
    @EnvironmentObject var deferLinkService: DeferLinkService
    
    var body: some View {
        NavigationView {
            List {
                if deferLinkService.testResults.isEmpty {
                    Section {
                        Text("Нет результатов тестов")
                            .foregroundColor(.secondary)
                    }
                } else {
                    // Summary Section
                    Section("Сводка") {
                        let stats = deferLinkService.getTestStatistics()
                        
                        if let totalTests = stats["total_tests"] as? Int {
                            StatRowView(label: "Всего тестов", value: "\(totalTests)")
                        }
                        
                        if let successRate = stats["success_rate"] as? Double {
                            StatRowView(label: "Процент успеха", value: String(format: "%.1f%%", successRate))
                        }
                        
                        if let matchRate = stats["match_rate"] as? Double {
                            StatRowView(label: "Процент совпадений", value: String(format: "%.1f%%", matchRate))
                        }
                        
                        if let avgDuration = stats["average_duration"] as? Double {
                            StatRowView(label: "Среднее время", value: String(format: "%.2fs", avgDuration))
                        }
                    }
                    
                    // Detailed Results
                    Section("Детальные результаты") {
                        ForEach(Array(deferLinkService.testResults.enumerated()), id: \.offset) { index, result in
                            DetailedTestResultView(result: result, index: index + 1)
                        }
                    }
                }
                
                Section("Действия") {
                    Button("Экспортировать результаты") {
                        exportResults()
                    }
                    .disabled(deferLinkService.testResults.isEmpty)
                    
                    Button("Очистить результаты") {
                        deferLinkService.clearResults()
                    }
                    .foregroundColor(.red)
                    .disabled(deferLinkService.testResults.isEmpty)
                }
            }
            .navigationTitle("Детальные результаты")
        }
    }
    
    private func exportResults() {
        var report = "DeferLink Test Results Report\n"
        report += "Generated: \(Date())\n\n"
        
        let stats = deferLinkService.getTestStatistics()
        report += "Summary:\n"
        report += "- Total tests: \(stats["total_tests"] ?? 0)\n"
        report += "- Success rate: \(String(format: "%.1f%%", stats["success_rate"] as? Double ?? 0))\n"
        report += "- Match rate: \(String(format: "%.1f%%", stats["match_rate"] as? Double ?? 0))\n"
        report += "- Average duration: \(String(format: "%.2fs", stats["average_duration"] as? Double ?? 0))\n\n"
        
        report += "Detailed Results:\n"
        for (index, result) in deferLinkService.testResults.enumerated() {
            report += "\nTest \(index + 1):\n"
            report += "- Status: \(result.statusDescription)\n"
            report += "- Duration: \(String(format: "%.2f", result.duration))s\n"
            report += "- Timestamp: \(result.timestamp)\n"
            
            if let response = result.response {
                report += "- Success: \(response.success)\n"
                report += "- Matched: \(response.matched)\n"
                report += "- Session ID: \(response.sessionId ?? "N/A")\n"
            }
            
            if let error = result.error {
                report += "- Error: \(error)\n"
            }
        }
        
        let activityController = UIActivityViewController(
            activityItems: [report],
            applicationActivities: nil
        )
        
        if let windowScene = UIApplication.shared.connectedScenes.first as? UIWindowScene,
           let window = windowScene.windows.first {
            window.rootViewController?.present(activityController, animated: true)
        }
    }
}

// MARK: - Detailed Test Result View
struct DetailedTestResultView: View {
    let result: TestResult
    let index: Int
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Тест #\(index)")
                    .font(.headline)
                Spacer()
                Text(result.statusDescription)
                    .font(.subheadline)
                    .foregroundColor(result.isSuccess ? .green : .red)
            }
            
            HStack {
                Text("Время:")
                Spacer()
                Text("\(String(format: "%.3f", result.duration))s")
            }
            .font(.caption)
            
            HStack {
                Text("Timestamp:")
                Spacer()
                Text(DateFormatter.localizedString(from: result.timestamp, dateStyle: .short, timeStyle: .medium))
            }
            .font(.caption)
            
            if let response = result.response {
                Group {
                    HStack {
                        Text("Session ID:")
                        Spacer()
                        Text(response.sessionId ?? "N/A")
                    }
                    
                    HStack {
                        Text("Promo ID:")
                        Spacer()
                        Text(response.promoId ?? "N/A")
                    }
                    
                    HStack {
                        Text("Domain:")
                        Spacer()
                        Text(response.domain ?? "N/A")
                    }
                }
                .font(.caption)
                .foregroundColor(.secondary)
            }
            
            if let error = result.error {
                Text("Ошибка: \(error)")
                    .font(.caption)
                    .foregroundColor(.red)
            }
        }
        .padding()
        .background(Color(.systemGray6))
        .cornerRadius(8)
    }
}
