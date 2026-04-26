//
//  SKANState.swift
//  DeferLinkSDK
//
//  Persistent state tracking for SKAdNetwork conversion-value computation.
//
//  We persist counters in UserDefaults under a single key — small enough
//  to be cheap, durable across launches, and survives app updates. The
//  state covers the SKAN conversion window (default 48h after install).
//

import Foundation

struct SKANState: Codable {
    var installDate:        Date
    var revenueUSD:         Double
    var sessionCount:       Int
    var totalSessionSeconds: Double
    var coreActionCount:    Int
    var lastSessionDate:    Date?
    var returnedNextDay:    Bool
    var retainedDayTwo:     Bool
    var lastCV:             Int    // last value sent to Apple
    var lastUpdate:         Date

    static let initial = SKANState(
        installDate:        Date(),
        revenueUSD:         0,
        sessionCount:       0,
        totalSessionSeconds: 0,
        coreActionCount:    0,
        lastSessionDate:    nil,
        returnedNextDay:    false,
        retainedDayTwo:     false,
        lastCV:             0,
        lastUpdate:         Date()
    )
}

final class SKANStateStore {

    private let defaultsKey = "com.deferlink.sdk.skan_state.v1"
    private let lock = NSLock()
    private var cache: SKANState?

    func load() -> SKANState {
        lock.lock(); defer { lock.unlock() }

        if let cached = cache { return cached }

        guard let data = UserDefaults.standard.data(forKey: defaultsKey),
              let state = try? JSONDecoder.iso8601.decode(SKANState.self, from: data) else {
            let fresh = SKANState.initial
            cache = fresh
            persist(fresh)
            return fresh
        }
        cache = state
        return state
    }

    func update(_ transform: (inout SKANState) -> Void) -> SKANState {
        lock.lock(); defer { lock.unlock() }

        var state = cache ?? load()
        transform(&state)
        state.lastUpdate = Date()
        cache = state
        persist(state)
        return state
    }

    func reset() {
        lock.lock(); defer { lock.unlock() }
        let fresh = SKANState.initial
        cache = fresh
        persist(fresh)
    }

    private func persist(_ state: SKANState) {
        guard let data = try? JSONEncoder.iso8601.encode(state) else { return }
        UserDefaults.standard.set(data, forKey: defaultsKey)
    }
}

private extension JSONEncoder {
    static let iso8601: JSONEncoder = {
        let e = JSONEncoder()
        e.dateEncodingStrategy = .iso8601
        return e
    }()
}

private extension JSONDecoder {
    static let iso8601: JSONDecoder = {
        let d = JSONDecoder()
        d.dateDecodingStrategy = .iso8601
        return d
    }()
}
