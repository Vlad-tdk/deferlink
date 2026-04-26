//
//  CVEncoder.swift
//  DeferLinkSDK
//
//  Swift port of the server-side cv_schema module — identical bit layout:
//    bits 5-3: revenue_bucket (3 bits, 8 log-scale USD buckets)
//    bits 2-1: engagement     (2 bits, bounce/active/deep/power)
//    bit 0:   event_flag      (1 bit, 1 = real conversion)
//

import Foundation

public enum EngagementTier: Int, Sendable {
    case bounce = 0
    case active = 1
    case deep   = 2
    case power  = 3
}

public struct CVComponents: Sendable {
    public let revenueBucket: Int   // 0..7
    public let engagement:    Int   // 0..3
    public let eventFlag:     Int   // 0..1

    public init(revenueBucket: Int, engagement: Int, eventFlag: Int) {
        precondition((0...7).contains(revenueBucket), "revenue_bucket out of range")
        precondition((0...3).contains(engagement),    "engagement out of range")
        precondition((0...1).contains(eventFlag),     "event_flag out of range")
        self.revenueBucket = revenueBucket
        self.engagement    = engagement
        self.eventFlag     = eventFlag
    }
}

public enum CVEncoder {

    /// Pack components into 6-bit value 0..63.
    public static func encode(_ c: CVComponents) -> Int {
        return (c.revenueBucket << 3) | (c.engagement << 1) | c.eventFlag
    }

    /// Map a USD amount to a revenue bucket 0..7.
    public static func revenueBucket(usd: Double, config: SKANConfig) -> Int {
        guard usd > 0 else { return 0 }
        var chosen = 0
        for (i, floor) in config.revenueBucketsUSD.enumerated() {
            if usd >= floor {
                chosen = i
            } else {
                break
            }
        }
        return chosen
    }

    /// Compute engagement tier 0..3 from raw metrics.
    public static func engagementTier(
        sessions: Int,
        totalSeconds: Double,
        coreActions: Int,
        returnedNextDay: Bool,
        retainedDayTwo: Bool,
        config: SKANConfig
    ) -> Int {
        let t = config.engagementThresholds

        if t.powerRequiresRetention &&
           returnedNextDay && retainedDayTwo &&
           coreActions >= t.deepMinCoreActions {
            return EngagementTier.power.rawValue
        }

        if sessions >= t.deepMinSessions || coreActions >= t.deepMinCoreActions {
            return EngagementTier.deep.rawValue
        }

        if sessions >= t.activeMinSessions ||
           totalSeconds >= Double(t.bounceMaxSeconds * 4) {
            return EngagementTier.active.rawValue
        }

        return EngagementTier.bounce.rawValue
    }

    /// High-level entry point — takes raw metrics, returns fine CV 0..63.
    public static func computeCV(
        revenueUSD:       Double,
        sessions:         Int,
        totalSeconds:     Double,
        coreActions:      Int,
        returnedNextDay:  Bool,
        retainedDayTwo:   Bool,
        isConversion:     Bool,
        config:           SKANConfig
    ) -> Int {
        let components = CVComponents(
            revenueBucket: revenueBucket(usd: revenueUSD, config: config),
            engagement:    engagementTier(
                sessions: sessions,
                totalSeconds: totalSeconds,
                coreActions: coreActions,
                returnedNextDay: returnedNextDay,
                retainedDayTwo: retainedDayTwo,
                config: config
            ),
            eventFlag: isConversion ? 1 : 0
        )
        return encode(components)
    }
}
