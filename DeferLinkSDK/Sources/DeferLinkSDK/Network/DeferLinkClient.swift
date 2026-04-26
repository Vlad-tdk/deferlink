// DeferLinkClient.swift
// DeferLinkSDK
//
// HTTP-клиент для взаимодействия с DeferLink сервером.
// Все запросы — async/await, никаких глобальных синглтонов.

import Foundation

final class DeferLinkClient {

    private let config:  DeferLinkConfiguration
    private let session: URLSession

    init(config: DeferLinkConfiguration) {
        self.config = config

        let cfg = URLSessionConfiguration.default
        cfg.timeoutIntervalForRequest  = config.networkTimeout
        cfg.timeoutIntervalForResource = config.networkTimeout * 3
        self.session = URLSession(configuration: cfg)
    }

    // MARK: - Resolve

    /// POST /resolve — основной запрос матчинга.
    func resolve(payload: FingerprintPayload, appScheme: String? = nil) async throws -> ResolveResponseBody {
        let url = try buildURL(path: "/resolve")

        let body = ResolveRequestBody(
            fingerprint: payload,
            appScheme:   appScheme,
            fallbackUrl: nil
        )

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(body)

        DeferLinkLogger.debug("POST \(url)")
        let (data, response) = try await session.data(for: request)
        try validate(response: response, data: data)

        do {
            return try JSONDecoder().decode(ResolveResponseBody.self, from: data)
        } catch {
            throw DeferLinkError.decodingError(error)
        }
    }

    // MARK: - Safari Cookie Resolve

    /// GET /safari-resolve → читает session_id из cookie (вызывается из SFSafariViewController).
    func safariResolveURL() throws -> URL {
        try buildURL(path: "/safari-resolve")
    }

    // MARK: - Events

    /// POST /api/v1/events/batch — send a batch of events.
    func sendEvents(_ events: [DeferLinkEvent]) async throws -> EventBatchResponse {
        let url = try buildURL(path: "/api/v1/events/batch")

        struct BatchBody: Encodable { let events: [DeferLinkEvent] }
        let body = BatchBody(events: events)

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(body)

        DeferLinkLogger.debug("POST \(url) (\(events.count) events)")
        let (data, response) = try await session.data(for: request)
        try validate(response: response, data: data)

        do {
            return try JSONDecoder().decode(EventBatchResponse.self, from: data)
        } catch {
            throw DeferLinkError.decodingError(error)
        }
    }

    // MARK: - SKAdNetwork

    /// GET /api/v1/skan/config?app_id=… — fetch CV encoding configuration.
    func fetchSKANConfig(appId: String) async throws -> SKANConfig {
        var components = URLComponents(
            url: try buildURL(path: "/api/v1/skan/config"),
            resolvingAgainstBaseURL: false
        )
        components?.queryItems = [URLQueryItem(name: "app_id", value: appId)]
        guard let url = components?.url else {
            throw DeferLinkError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = "GET"

        DeferLinkLogger.debug("GET \(url)")
        let (data, response) = try await session.data(for: request)
        try validate(response: response, data: data)

        do {
            return try JSONDecoder().decode(SKANConfig.self, from: data)
        } catch {
            throw DeferLinkError.decodingError(error)
        }
    }

    // MARK: - Health Check

    func healthCheck() async -> Bool {
        guard let url = try? buildURL(path: "/api/v1/health") else { return false }
        let result = try? await session.data(from: url)
        guard let (_, response) = result else { return false }
        return (response as? HTTPURLResponse)?.statusCode == 200
    }

    // MARK: - Helpers

    private func buildURL(path: String) throws -> URL {
        guard let url = URL(string: config.baseURL + path) else {
            throw DeferLinkError.invalidURL
        }
        return url
    }

    private func validate(response: URLResponse, data: Data) throws {
        guard let http = response as? HTTPURLResponse else { return }
        guard (200..<300).contains(http.statusCode) else {
            let msg = String(data: data, encoding: .utf8)
            throw DeferLinkError.serverError(http.statusCode, msg)
        }
    }
}
