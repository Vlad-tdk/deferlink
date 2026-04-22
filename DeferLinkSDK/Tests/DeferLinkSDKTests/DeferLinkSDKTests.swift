// DeferLinkSDKTests.swift
// DeferLinkSDK

import XCTest
@testable import DeferLinkSDK

final class DeferLinkSDKTests: XCTestCase {

    // MARK: - Configuration

    func testConfiguration_trailingSlashStripped() {
        let cfg = DeferLinkConfiguration(baseURL: "https://api.example.com/")
        XCTAssertEqual(cfg.baseURL, "https://api.example.com")
    }

    func testConfiguration_defaults() {
        let cfg = DeferLinkConfiguration(baseURL: "https://api.example.com")
        XCTAssertEqual(cfg.appURLScheme,        "deferlink")
        XCTAssertEqual(cfg.clipboardTokenPrefix, "deferlink")
        XCTAssertEqual(cfg.networkTimeout,       10.0)
        XCTAssertFalse(cfg.debugLogging)
    }

    // MARK: - Clipboard Token Parsing

    func testClipboardToken_validPrefix() {
        let config    = DeferLinkConfiguration(baseURL: "https://x.com")
        let collector = FingerprintCollector(config: config)

        // Имитируем содержимое clipboard
        UIPasteboard.general.string = "deferlink:abc-123-def"
        let token = collector.readClipboardToken()
        XCTAssertEqual(token, "abc-123-def")
    }

    func testClipboardToken_wrongPrefix_returnsNil() {
        let config    = DeferLinkConfiguration(baseURL: "https://x.com")
        let collector = FingerprintCollector(config: config)

        UIPasteboard.general.string = "someotherapp:abc-123-def"
        XCTAssertNil(collector.readClipboardToken())
    }

    func testClipboardToken_tooShort_returnsNil() {
        let config    = DeferLinkConfiguration(baseURL: "https://x.com")
        let collector = FingerprintCollector(config: config)

        UIPasteboard.general.string = "deferlink:short"
        XCTAssertNil(collector.readClipboardToken())
    }

    func testClipboardToken_empty_returnsNil() {
        let config    = DeferLinkConfiguration(baseURL: "https://x.com")
        let collector = FingerprintCollector(config: config)

        UIPasteboard.general.string = ""
        XCTAssertNil(collector.readClipboardToken())
    }

    func testClipboardToken_clearsAfterRead() {
        let config    = DeferLinkConfiguration(baseURL: "https://x.com")
        let collector = FingerprintCollector(config: config)
        let sessionId = "abcdef1234567890abcdef1234567890abcd"

        UIPasteboard.general.string = "deferlink:\(sessionId)"
        _ = collector.readClipboardToken()
        XCTAssertEqual(UIPasteboard.general.string, "")
    }

    // MARK: - First Launch Flag

    func testFirstLaunch_initiallyTrue() {
        let config    = DeferLinkConfiguration(baseURL: "https://x.com")
        let collector = FingerprintCollector(config: config)
        // Сбрасываем флаг перед тестом
        UserDefaults.standard.removeObject(forKey: "com.deferlink.sdk.first_launch_done")
        XCTAssertTrue(collector.isFirstLaunch)
    }

    func testFirstLaunch_falseAfterMark() {
        let config    = DeferLinkConfiguration(baseURL: "https://x.com")
        let collector = FingerprintCollector(config: config)
        collector.markFirstLaunchDone()
        XCTAssertFalse(collector.isFirstLaunch)
        // Cleanup
        UserDefaults.standard.removeObject(forKey: "com.deferlink.sdk.first_launch_done")
    }

    // MARK: - Models

    func testResolveResponseBody_decodingSuccess() throws {
        let json = """
        {
            "success": true,
            "promo_id": "SUMMER24",
            "domain": "myapp.com",
            "session_id": "uuid-123",
            "app_url": "myapp://promo/SUMMER24",
            "matched": true,
            "match_method": "clipboard",
            "message": "OK"
        }
        """.data(using: .utf8)!

        let response = try JSONDecoder().decode(ResolveResponseBody.self, from: json)
        XCTAssertTrue(response.matched)
        XCTAssertEqual(response.promoId, "SUMMER24")
        XCTAssertEqual(response.matchMethod, "clipboard")

        let result = response.toDeferLinkResult()
        XCTAssertEqual(result.matchMethod, .clipboard)
        XCTAssertEqual(result.promoId, "SUMMER24")
    }

    func testResolveResponseBody_noMatch() throws {
        let json = """
        {"success": false, "matched": false, "message": "Not found"}
        """.data(using: .utf8)!

        let response = try JSONDecoder().decode(ResolveResponseBody.self, from: json)
        XCTAssertFalse(response.matched)
        XCTAssertNil(response.promoId)
        XCTAssertNil(response.matchMethod)
    }

    func testDeferLinkResult_matchMethods() {
        XCTAssertEqual(DeferLinkResult.MatchMethod(rawValue: "clipboard"),    .clipboard)
        XCTAssertEqual(DeferLinkResult.MatchMethod(rawValue: "safari_cookie"), .safariCookie)
        XCTAssertEqual(DeferLinkResult.MatchMethod(rawValue: "device_check"),  .deviceCheck)
        XCTAssertEqual(DeferLinkResult.MatchMethod(rawValue: "fingerprint"),   .fingerprint)
        XCTAssertNil(DeferLinkResult.MatchMethod(rawValue: "unknown_future_value"))
    }

    // MARK: - FingerprintPayload encoding

    func testFingerprintPayload_encodesNilFieldsOmitted() throws {
        let payload = FingerprintPayload(
            model: "iPhone15,2",
            language: "ru_RU",
            timezone: "Europe/Moscow",
            userAgent: nil,
            screenWidth: 390,
            screenHeight: 844,
            platform: "iOS",
            appVersion: "1.0",
            idfv: nil,
            clipboardToken: "token-123",
            deviceCheckToken: nil,
            safariCookieSessionId: nil,
            isFirstLaunch: true
        )

        let data = try JSONEncoder().encode(payload)
        let dict = try JSONSerialization.jsonObject(with: data) as! [String: Any]

        XCTAssertEqual(dict["model"] as? String,         "iPhone15,2")
        XCTAssertEqual(dict["clipboard_token"] as? String, "token-123")
        XCTAssertEqual(dict["is_first_launch"] as? Bool,  true)
        XCTAssertNil(dict["device_check_token"])   // nil не кодируется
    }

    // MARK: - Error descriptions

    func testDeferLinkError_notConfigured() {
        let error = DeferLinkError.notConfigured
        XCTAssertFalse(error.errorDescription!.isEmpty)
    }

    func testDeferLinkError_serverError() {
        let error = DeferLinkError.serverError(429, "Too many requests")
        XCTAssertTrue(error.errorDescription!.contains("429"))
    }

    // MARK: - URL handling

    func testHandleOpenURL_safariResolvedURL() async throws {
        await DeferLink.configure(baseURL: "https://api.example.com", appURLScheme: "myapp")

        let url = URL(string: "myapp://resolved?session_id=test-session-id")!
        let handled = await DeferLink.shared.handleOpenURL(url)
        XCTAssertTrue(handled)
    }

    func testHandleOpenURL_wrongScheme_returnsFalse() async {
        await DeferLink.configure(baseURL: "https://api.example.com", appURLScheme: "myapp")
        let url = URL(string: "otherapp://resolved?session_id=x")!
        let handled = await DeferLink.shared.handleOpenURL(url)
        XCTAssertFalse(handled)
    }

    // MARK: - DeferLinkEvent

    func testEvent_defaultFieldsArePopulated() {
        let ev = DeferLinkEvent(eventName: "af_content_view")
        XCTAssertFalse(ev.eventId.isEmpty)
        XCTAssertEqual(ev.eventName, "af_content_view")
        XCTAssertFalse(ev.timestamp.isEmpty)
        XCTAssertEqual(ev.platform, "iOS")
        XCTAssertEqual(ev.currency, "USD")
        XCTAssertNil(ev.revenue)
    }

    func testEvent_purchaseConvenience() {
        let ev = DeferLinkEvent.purchase(9.99, currency: "EUR", properties: ["item_id": "pro"])
        XCTAssertEqual(ev.eventName, DLEventName.purchase)
        XCTAssertEqual(ev.revenue,   9.99)
        XCTAssertEqual(ev.currency,  "EUR")
        XCTAssertNotNil(ev.properties?["item_id"])
    }

    func testEvent_registrationConvenience() {
        let ev = DeferLinkEvent.registration(method: "apple")
        XCTAssertEqual(ev.eventName, DLEventName.completeRegistration)
        XCTAssertNotNil(ev.properties?["registration_method"])
    }

    func testEvent_encodesToJSON() throws {
        let ev = DeferLinkEvent(
            eventName:  "af_purchase",
            revenue:    29.99,
            currency:   "USD",
            properties: ["order_id": "ORD123"]
        )
        let data = try JSONEncoder().encode(ev)
        let dict = try JSONSerialization.jsonObject(with: data) as! [String: Any]
        XCTAssertEqual(dict["event_name"] as? String,  "af_purchase")
        XCTAssertEqual(dict["revenue"]    as? Double,  29.99)
        XCTAssertFalse((dict["event_id"] as? String ?? "").isEmpty)
        let props = dict["properties"] as? [String: Any]
        XCTAssertEqual(props?["order_id"] as? String, "ORD123")
    }

    func testEvent_roundTripsJSON() throws {
        let ev = DeferLinkEvent(eventName: "af_login", properties: ["method": "google"])
        let data = try JSONEncoder().encode(ev)
        let decoded = try JSONDecoder().decode(DeferLinkEvent.self, from: data)
        XCTAssertEqual(decoded.eventId,   ev.eventId)
        XCTAssertEqual(decoded.eventName, ev.eventName)
        XCTAssertEqual(decoded.timestamp, ev.timestamp)
    }

    // MARK: - EventQueue

    func testEventQueue_enqueueAndDrain() {
        let q = EventQueue()
        // Clean slate
        q.drain { _ in }

        let ev = DeferLinkEvent(eventName: "af_test")
        q.enqueue([ev])

        let expectation = self.expectation(description: "drain")
        var drained: [DeferLinkEvent] = []
        // Small delay so the serial queue processes enqueue first
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
            q.drain { events in
                drained = events
                expectation.fulfill()
            }
        }
        waitForExpectations(timeout: 2)
        XCTAssertEqual(drained.count, 1)
        XCTAssertEqual(drained.first?.eventName, "af_test")
    }

    func testEventQueue_drainClearsQueue() {
        let q = EventQueue()
        q.enqueue([DeferLinkEvent(eventName: "af_launch")])

        let exp = expectation(description: "second drain")
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
            q.drain { _ in
                // first drain consumed events
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                    q.drain { second in
                        XCTAssertTrue(second.isEmpty, "Queue should be empty after first drain")
                        exp.fulfill()
                    }
                }
            }
        }
        waitForExpectations(timeout: 3)
    }

    // MARK: - Standard event name constants

    func testStandardEventNames_areCorrect() {
        XCTAssertEqual(DLEventName.purchase,             "af_purchase")
        XCTAssertEqual(DLEventName.completeRegistration, "af_complete_registration")
        XCTAssertEqual(DLEventName.subscribe,            "af_subscribe")
        XCTAssertEqual(DLEventName.addToCart,            "af_add_to_cart")
        XCTAssertEqual(DLEventName.login,                "af_login")
    }

    // MARK: - AnyCodable

    func testAnyCodable_encodesString() throws {
        let v = AnyCodable("hello")
        let d = try JSONEncoder().encode(v)
        XCTAssertEqual(String(data: d, encoding: .utf8), "\"hello\"")
    }

    func testAnyCodable_encodesDouble() throws {
        let v = AnyCodable(3.14)
        let d = try JSONEncoder().encode(v)
        XCTAssertEqual(String(data: d, encoding: .utf8), "3.14")
    }

    func testAnyCodable_encodesBool() throws {
        let v = AnyCodable(true)
        let d = try JSONEncoder().encode(v)
        XCTAssertEqual(String(data: d, encoding: .utf8), "true")
    }
}
