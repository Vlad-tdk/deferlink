// DeferLinkEvent.swift
// DeferLinkSDK
//
// Event model + standard event name constants (mirrors AppsFlyer naming).

import Foundation

// MARK: - DeferLinkEvent

/// A single analytics event.
///
/// Create with the convenience initialiser or ``DeferLinkEvent.purchase(_:currency:properties:)``.
/// Pass to ``DeferLink/shared/logEvent(_:)`` or ``DeferLink/shared/logEvent(_:revenue:currency:properties:)``.
public struct DeferLinkEvent: Encodable {

    // ── Identity ────────────────────────────────────────────────────────────
    /// Client-generated UUID. Used as deduplication key on the server.
    public let eventId: String

    /// The name of the event, e.g. ``DLEventName.purchase``.
    public let eventName: String

    /// Client-side timestamp (ISO 8601). Defaults to `Date()`.
    public let timestamp: String

    // ── Attribution context (populated automatically by the SDK) ─────────
    /// `session_id` from the resolved deep link (attribution).
    public var sessionId: String?

    /// Your app's user identifier.
    public var appUserId: String?

    /// `promo_id` from the resolved deep link.
    public var promoId: String?

    // ── Revenue ─────────────────────────────────────────────────────────────
    /// Monetary value — use for purchase / subscription events.
    public var revenue: Double?

    /// ISO 4217 currency code, e.g. "USD". Defaults to "USD".
    public var currency: String

    // ── Custom properties ───────────────────────────────────────────────────
    /// Up to 50 key-value pairs. Values must be JSON-serialisable.
    public var properties: [String: AnyCodable]?

    // ── Device / app context (auto-filled by SDK) ───────────────────────────
    public var platform: String
    public var appVersion: String?
    public var sdkVersion: String

    // MARK: Init

    public init(
        eventName:   String,
        revenue:     Double?               = nil,
        currency:    String                = "USD",
        properties:  [String: Any]?        = nil,
        appUserId:   String?               = nil
    ) {
        self.eventId    = UUID().uuidString
        self.eventName  = eventName
        self.timestamp  = ISO8601DateFormatter().string(from: Date())
        self.revenue    = revenue
        self.currency   = currency
        self.appUserId  = appUserId
        self.platform   = "iOS"
        self.sdkVersion = DeferLinkSDKInfo.version

        if let props = properties {
            self.properties = props.mapValues { AnyCodable($0) }
        }
        self.appVersion = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String
    }

    // MARK: CodingKeys

    enum CodingKeys: String, CodingKey {
        case eventId    = "event_id"
        case eventName  = "event_name"
        case timestamp
        case sessionId  = "session_id"
        case appUserId  = "app_user_id"
        case promoId    = "promo_id"
        case revenue
        case currency
        case properties
        case platform
        case appVersion = "app_version"
        case sdkVersion = "sdk_version"
    }
}

// MARK: - Convenience factories

public extension DeferLinkEvent {

    /// Convenience: purchase event.
    static func purchase(
        _ revenue: Double,
        currency:   String             = "USD",
        properties: [String: Any]?     = nil,
        appUserId:  String?            = nil
    ) -> DeferLinkEvent {
        DeferLinkEvent(
            eventName:  DLEventName.purchase,
            revenue:    revenue,
            currency:   currency,
            properties: properties,
            appUserId:  appUserId
        )
    }

    /// Convenience: subscription event.
    static func subscribe(
        _ revenue: Double,
        currency:  String            = "USD",
        properties: [String: Any]?   = nil
    ) -> DeferLinkEvent {
        DeferLinkEvent(
            eventName:  DLEventName.subscribe,
            revenue:    revenue,
            currency:   currency,
            properties: properties
        )
    }

    /// Convenience: registration completed.
    static func registration(method: String? = nil) -> DeferLinkEvent {
        var props: [String: Any]? = nil
        if let m = method { props = ["registration_method": m] }
        return DeferLinkEvent(eventName: DLEventName.completeRegistration, properties: props)
    }
}

// MARK: - Standard event names (af_ prefix, mirrors AppsFlyer)

public enum DLEventName {
    public static let install              = "af_install"
    public static let launch               = "af_launch"
    public static let completeRegistration = "af_complete_registration"
    public static let login                = "af_login"
    public static let purchase             = "af_purchase"
    public static let addToCart            = "af_add_to_cart"
    public static let addToWishlist        = "af_add_to_wishlist"
    public static let initiatedCheckout    = "af_initiated_checkout"
    public static let contentView          = "af_content_view"
    public static let search               = "af_search"
    public static let subscribe            = "af_subscribe"
    public static let levelAchieved        = "af_level_achieved"
    public static let tutorialCompletion   = "af_tutorial_completion"
    public static let rate                 = "af_rate"
    public static let share                = "af_share"
    public static let invite               = "af_invite"
    public static let reEngage             = "af_re_engage"
    public static let update               = "af_update"
}

// MARK: - Standard property keys

public enum DLEventParam {
    public static let contentId      = "af_content_id"
    public static let contentType    = "af_content_type"
    public static let currency       = "af_currency"
    public static let revenue        = "af_revenue"
    public static let price          = "af_price"
    public static let quantity       = "af_quantity"
    public static let orderId        = "af_order_id"
    public static let level          = "af_level"
    public static let score          = "af_score"
    public static let searchString   = "af_search_string"
    public static let registrationMethod = "af_registration_method"
    public static let description    = "af_description"
}

// MARK: - SDK version constant

enum DeferLinkSDKInfo {
    static let version = "1.0.0"
}

// MARK: - AnyCodable (lightweight type-erased Encodable)

/// Allows heterogeneous `[String: Any]` dictionaries to be Encodable.
public struct AnyCodable: Codable {
    public let value: Any

    public init(_ value: Any) { self.value = value }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch value {
        case let v as Bool:   try container.encode(v)
        case let v as Int:    try container.encode(v)
        case let v as Double: try container.encode(v)
        case let v as Float:  try container.encode(Double(v))
        case let v as String: try container.encode(v)
        case let v as [Any]:
            try container.encode(v.map { AnyCodable($0) })
        case let v as [String: Any]:
            try container.encode(v.mapValues { AnyCodable($0) })
        default:
            try container.encode(String(describing: value))
        }
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let v = try? container.decode(Bool.self)             { value = v }
        else if let v = try? container.decode(Int.self)         { value = v }
        else if let v = try? container.decode(Double.self)      { value = v }
        else if let v = try? container.decode(String.self)      { value = v }
        else if let v = try? container.decode([AnyCodable].self) { value = v.map(\.value) }
        else if let v = try? container.decode([String: AnyCodable].self) {
            value = v.mapValues(\.value)
        } else {
            value = NSNull()
        }
    }
}
