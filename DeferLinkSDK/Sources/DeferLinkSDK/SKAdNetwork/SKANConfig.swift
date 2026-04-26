//
//  SKANConfig.swift
//  DeferLinkSDK
//
//  CV encoding configuration — mirrors the server-side SKANConfig.
//  Fetched from the backend at SDK startup with a non-blocking background
//  refresh; the baked-in defaults are used until the first successful fetch.
//

import Foundation

public struct SKANEngagementThresholds: Codable, Sendable {
    public let bounceMaxSeconds:       Int
    public let activeMinSessions:      Int
    public let deepMinSessions:        Int
    public let deepMinCoreActions:     Int
    public let powerRequiresRetention: Bool

    enum CodingKeys: String, CodingKey {
        case bounceMaxSeconds       = "bounce_max_seconds"
        case activeMinSessions      = "active_min_sessions"
        case deepMinSessions        = "deep_min_sessions"
        case deepMinCoreActions     = "deep_min_core_actions"
        case powerRequiresRetention = "power_requires_retention"
    }

    public static let defaults = SKANEngagementThresholds(
        bounceMaxSeconds:       30,
        activeMinSessions:      2,
        deepMinSessions:        5,
        deepMinCoreActions:     1,
        powerRequiresRetention: true
    )
}

public struct SKANConfig: Codable, Sendable {
    public let appId:                String
    public let schemaVersion:        Int
    public let schemaName:           String
    public let revenueBucketsUSD:    [Double]
    public let engagementThresholds: SKANEngagementThresholds
    public let conversionWindowHours: Int
    public let cacheTTLSeconds:      Int

    enum CodingKeys: String, CodingKey {
        case appId                = "app_id"
        case schemaVersion        = "schema_version"
        case schemaName           = "schema_name"
        case revenueBucketsUSD    = "revenue_buckets_usd"
        case engagementThresholds = "engagement_thresholds"
        case conversionWindowHours = "conversion_window_hours"
        case cacheTTLSeconds      = "cache_ttl_seconds"
    }

    /// Defaults — exactly matches the server's DEFAULT_REVENUE_BUCKETS and
    /// DEFAULT_ENGAGEMENT_THRESHOLDS. Used when backend is unreachable.
    public static func bundledDefaults(appId: String) -> SKANConfig {
        SKANConfig(
            appId:                 appId,
            schemaVersion:         1,
            schemaName:            "rev3_eng2_flag1",
            revenueBucketsUSD:     [0.0, 0.01, 1.0, 5.0, 20.0, 50.0, 100.0, 300.0],
            engagementThresholds:  .defaults,
            conversionWindowHours: 48,
            cacheTTLSeconds:       86400
        )
    }
}
