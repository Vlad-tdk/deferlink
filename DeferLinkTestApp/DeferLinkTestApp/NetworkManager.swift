//
//  NetworkManager.swift
//  DeferLinkTestApp
//
//  Created by Vladimir Martemianov on 3. 6. 2025..
//

import Foundation

class NetworkManager: ObservableObject {
    static let shared = NetworkManager()
    
    @Published var baseURL: String = "http://localhost:8000"
    @Published var isConnected: Bool = false
    
    private let session = URLSession.shared
    
    private init() {
        checkConnection()
    }
    
    // MARK: - Connection Check
    func checkConnection() {
        guard let url = URL(string: "\(baseURL)/api/v1/health/quick") else { return }
        
        let task = session.dataTask(with: url) { [weak self] data, response, error in
            DispatchQueue.main.async {
                if let httpResponse = response as? HTTPURLResponse,
                   httpResponse.statusCode == 200 {
                    self?.isConnected = true
                    print("✅ Соединение с сервером установлено")
                } else {
                    self?.isConnected = false
                    print("❌ Нет соединения с сервером")
                }
            }
        }
        task.resume()
    }
    
    // MARK: - API Methods
    func resolveDeepLink(fingerprint: FingerprintData, completion: @escaping (Result<ResolveResponse, Error>) -> Void) {
        guard let url = URL(string: "\(baseURL)/resolve") else {
            completion(.failure(NetworkError.invalidURL))
            return
        }
        
        let request = ResolveRequest(
            fingerprint: fingerprint,
            appScheme: "defrtest://test",
            fallbackUrl: "https://apps.apple.com"
        )
        
        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = "POST"
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        do {
            urlRequest.httpBody = try JSONEncoder().encode(request)
        } catch {
            completion(.failure(error))
            return
        }
        
        let task = session.dataTask(with: urlRequest) { data, response, error in
            if let error = error {
                completion(.failure(error))
                return
            }
            
            guard let data = data else {
                completion(.failure(NetworkError.noData))
                return
            }
            
            do {
                let response = try JSONDecoder().decode(ResolveResponse.self, from: data)
                completion(.success(response))
            } catch {
                completion(.failure(error))
            }
        }
        
        task.resume()
    }
    
    func createBrowserSession(promoId: String, domain: String, completion: @escaping (Result<String, Error>) -> Void) {
        let urlString = "\(baseURL)/dl?promo_id=\(promoId)&domain=\(domain)"
        guard let url = URL(string: urlString) else {
            completion(.failure(NetworkError.invalidURL))
            return
        }
        
        var request = URLRequest(url: url)
        request.setValue(DeviceInfo.getUserAgent(), forHTTPHeaderField: "User-Agent")
        
        let task = session.dataTask(with: request) { data, response, error in
            if let error = error {
                completion(.failure(error))
                return
            }
            
            if let httpResponse = response as? HTTPURLResponse,
               httpResponse.statusCode == 200 {
                completion(.success("Browser session created"))
            } else {
                completion(.failure(NetworkError.serverError))
            }
        }
        
        task.resume()
    }
    
    func getStats(completion: @escaping (Result<[String: Any], Error>) -> Void) {
        guard let url = URL(string: "\(baseURL)/api/v1/stats") else {
            completion(.failure(NetworkError.invalidURL))
            return
        }
        
        let task = session.dataTask(with: url) { data, response, error in
            if let error = error {
                completion(.failure(error))
                return
            }
            
            guard let data = data else {
                completion(.failure(NetworkError.noData))
                return
            }
            
            do {
                if let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] {
                    completion(.success(json))
                } else {
                    completion(.failure(NetworkError.invalidResponse))
                }
            } catch {
                completion(.failure(error))
            }
        }
        
        task.resume()
    }
    
    // MARK: - Test Methods
    func simulateBrowserVisit(promoId: String, domain: String, completion: @escaping (Result<String, Error>) -> Void) {
        // Симулируем визит браузера с текущим устройством
        let fingerprint = FingerprintCollector.collectFingerprint()
        
        var urlComponents = URLComponents(string: "\(baseURL)/dl")!
        urlComponents.queryItems = [
            URLQueryItem(name: "promo_id", value: promoId),
            URLQueryItem(name: "domain", value: domain),
            URLQueryItem(name: "timezone", value: fingerprint.timezone),
            URLQueryItem(name: "language", value: fingerprint.language),
            URLQueryItem(name: "screen_size", value: "\(fingerprint.screenWidth ?? 0)x\(fingerprint.screenHeight ?? 0)"),
            URLQueryItem(name: "model", value: fingerprint.model)
        ]
        
        guard let url = urlComponents.url else {
            completion(.failure(NetworkError.invalidURL))
            return
        }
        
        var request = URLRequest(url: url)
        request.setValue(fingerprint.userAgent, forHTTPHeaderField: "User-Agent")
        
        let task = session.dataTask(with: request) { data, response, error in
            if let error = error {
                completion(.failure(error))
                return
            }
            
            if let httpResponse = response as? HTTPURLResponse,
               httpResponse.statusCode == 200 {
                completion(.success("Browser visit simulated successfully"))
            } else {
                completion(.failure(NetworkError.serverError))
            }
        }
        
        task.resume()
    }
}

// MARK: - Network Errors
enum NetworkError: LocalizedError {
    case invalidURL
    case noData
    case serverError
    case invalidResponse
    
    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Неверный URL"
        case .noData:
            return "Нет данных от сервера"
        case .serverError:
            return "Ошибка сервера"
        case .invalidResponse:
            return "Неверный формат ответа"
        }
    }
}
