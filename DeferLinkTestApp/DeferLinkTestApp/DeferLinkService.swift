//
//  DeferLinkService.swift
//  DeferLinkTestApp
//
//  Created by Vladimir Martemianov on 3. 6. 2025..
//

import Foundation

class DeferLinkService: ObservableObject {
    
    @Published var testResults: [TestResult] = []
    @Published var isLoading: Bool = false
    @Published var lastDeepLink: String?
    
    private let networkManager = NetworkManager.shared
    
    init() {
        // Подписываемся на уведомления о deep links
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(handleDeepLinkReceived),
            name: NSNotification.Name("DeepLinkReceived"),
            object: nil
        )
    }
    
    deinit {
        NotificationCenter.default.removeObserver(self)
    }
    
    // MARK: - Deep Link Handling
    @objc private func handleDeepLinkReceived(_ notification: Notification) {
        guard let userInfo = notification.userInfo,
              let url = userInfo["url"] as? String else { return }
        
        DispatchQueue.main.async {
            self.lastDeepLink = url
            print("🎯 Deep link получен в сервисе: \(url)")
        }
    }
    
    // MARK: - Test Methods
    func runSingleTest(promoId: String = "test2024", domain: String = "test.com") {
        isLoading = true
        
        let startTime = Date()
        let fingerprint = FingerprintCollector.collectFingerprint()
        
        networkManager.resolveDeepLink(fingerprint: fingerprint) { [weak self] result in
            DispatchQueue.main.async {
                let duration = Date().timeIntervalSince(startTime)
                
                let testResult: TestResult
                
                switch result {
                case .success(let response):
                    testResult = TestResult(
                        timestamp: Date(),
                        fingerprint: fingerprint,
                        response: response,
                        error: nil,
                        duration: duration
                    )
                    
                case .failure(let error):
                    testResult = TestResult(
                        timestamp: Date(),
                        fingerprint: fingerprint,
                        response: nil,
                        error: error.localizedDescription,
                        duration: duration
                    )
                }
                
                self?.testResults.insert(testResult, at: 0)
                self?.isLoading = false
            }
        }
    }
    
    func runFullTest(promoId: String = "test2024", domain: String = "test.com") {
        isLoading = true
        
        // Шаг 1: Симулируем визит браузера
        networkManager.simulateBrowserVisit(promoId: promoId, domain: domain) { [weak self] result in
            switch result {
            case .success(_):
                print("✅ Браузерная сессия создана")
                
                // Шаг 2: Ждем немного и тестируем resolve
                DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
                    self?.runSingleTest(promoId: promoId, domain: domain)
                }
                
            case .failure(let error):
                DispatchQueue.main.async {
                    let testResult = TestResult(
                        timestamp: Date(),
                        fingerprint: FingerprintCollector.collectFingerprint(),
                        response: nil,
                        error: "Ошибка создания браузерной сессии: \(error.localizedDescription)",
                        duration: 0
                    )
                    
                    self?.testResults.insert(testResult, at: 0)
                    self?.isLoading = false
                }
            }
        }
    }
    
    func runStressTest(count: Int = 10, promoId: String = "test2024", domain: String = "test.com") {
        isLoading = true
        
        let variations = FingerprintCollector.createTestVariations()
        var completedTests = 0
        
        for i in 0..<count {
            let fingerprint = variations[i % variations.count]
            let startTime = Date()
            
            // Добавляем задержку между запросами
            DispatchQueue.main.asyncAfter(deadline: .now() + Double(i) * 0.5) {
                self.networkManager.resolveDeepLink(fingerprint: fingerprint) { [weak self] result in
                    DispatchQueue.main.async {
                        let duration = Date().timeIntervalSince(startTime)
                        
                        let testResult: TestResult
                        
                        switch result {
                        case .success(let response):
                            testResult = TestResult(
                                timestamp: Date(),
                                fingerprint: fingerprint,
                                response: response,
                                error: nil,
                                duration: duration
                            )
                            
                        case .failure(let error):
                            testResult = TestResult(
                                timestamp: Date(),
                                fingerprint: fingerprint,
                                response: nil,
                                error: error.localizedDescription,
                                duration: duration
                            )
                        }
                        
                        self?.testResults.insert(testResult, at: 0)
                        
                        completedTests += 1
                        if completedTests >= count {
                            self?.isLoading = false
                        }
                    }
                }
            }
        }
    }
    
    func clearResults() {
        testResults.removeAll()
    }
    
    // MARK: - Statistics
    func getTestStatistics() -> [String: Any] {
        guard !testResults.isEmpty else {
            return ["message": "Нет результатов тестов"]
        }
        
        let totalTests = testResults.count
        let successfulTests = testResults.filter { $0.isSuccess }.count
        let failedTests = totalTests - successfulTests
        let averageDuration = testResults.map { $0.duration }.reduce(0, +) / Double(totalTests)
        
        let matchedTests = testResults.compactMap { $0.response }.filter { $0.matched }.count
        let unmatchedTests = testResults.compactMap { $0.response }.filter { !$0.matched }.count
        
        return [
            "total_tests": totalTests,
            "successful_tests": successfulTests,
            "failed_tests": failedTests,
            "success_rate": Double(successfulTests) / Double(totalTests) * 100,
            "matched_tests": matchedTests,
            "unmatched_tests": unmatchedTests,
            "match_rate": totalTests > 0 ? Double(matchedTests) / Double(totalTests) * 100 : 0,
            "average_duration": averageDuration
        ]
    }
    
    // MARK: - Test Scenarios
    func runScenarioTest(scenario: TestScenario) {
        isLoading = true
        
        switch scenario {
        case .immediateResolve:
            // Симулируем браузерную сессию и сразу resolve
            networkManager.simulateBrowserVisit(promoId: "immediate", domain: "test.com") { [weak self] _ in
                DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
                    self?.runSingleTest(promoId: "immediate", domain: "test.com")
                }
            }
            
        case .delayedResolve:
            // Симулируем браузерную сессию и resolve через 30 секунд
            networkManager.simulateBrowserVisit(promoId: "delayed", domain: "test.com") { [weak self] _ in
                DispatchQueue.main.asyncAfter(deadline: .now() + 30.0) {
                    self?.runSingleTest(promoId: "delayed", domain: "test.com")
                }
            }
            
        case .noMatchTest:
            // Тестируем resolve без предварительной браузерной сессии
            runSingleTest(promoId: "nomatch", domain: "test.com")
            
        case .multipleDevices:
            // Симулируем несколько разных устройств
            let variations = FingerprintCollector.createTestVariations()
            runStressTest(count: variations.count, promoId: "multi", domain: "test.com")
        }
    }
}

// MARK: - Test Scenarios
enum TestScenario: String, CaseIterable {
    case immediateResolve = "Немедленное разрешение"
    case delayedResolve = "Отложенное разрешение (30с)"
    case noMatchTest = "Тест без совпадений"
    case multipleDevices = "Множественные устройства"
    
    var description: String {
        switch self {
        case .immediateResolve:
            return "Создает браузерную сессию и сразу пытается разрешить диплинк"
        case .delayedResolve:
            return "Создает браузерную сессию и разрешает диплинк через 30 секунд"
        case .noMatchTest:
            return "Пытается разрешить диплинк без предварительной браузерной сессии"
        case .multipleDevices:
            return "Тестирует различные вариации fingerprint устройств"
        }
    }
}
