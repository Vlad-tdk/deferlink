// EventQueue.swift
// DeferLinkSDK
//
// Offline-first event queue.
//
// ▸ Events are appended to a JSON file in Application Support.
// ▸ On successful flush the file is trimmed (only failed events remain).
// ▸ Thread-safety: all mutations go through a serial DispatchQueue.
// ▸ Max 500 persisted events — oldest are dropped when the cap is hit.

import Foundation

// MARK: - EventQueue

final class EventQueue {

    // MARK: - Constants

    private static let filename  = "com.deferlink.sdk.event_queue.json"
    private static let maxEvents = 500

    // MARK: - State

    private let queue   = DispatchQueue(label: "com.deferlink.sdk.eventqueue", qos: .utility)
    private let fileURL: URL

    // MARK: - Init

    init() {
        let support = FileManager.default
            .urls(for: .applicationSupportDirectory, in: .userDomainMask)
            .first ?? FileManager.default.temporaryDirectory

        // Make sure directory exists
        try? FileManager.default.createDirectory(at: support, withIntermediateDirectories: true)
        fileURL = support.appendingPathComponent(EventQueue.filename)
    }

    // MARK: - Enqueue

    /// Append events to the persistent queue. Caps at `maxEvents` (FIFO drop).
    func enqueue(_ events: [DeferLinkEvent]) {
        guard !events.isEmpty else { return }
        queue.async { [weak self] in
            guard let self = self else { return }
            var stored = self.load()
            stored.append(contentsOf: events)
            // Drop oldest if over cap
            if stored.count > EventQueue.maxEvents {
                stored = Array(stored.suffix(EventQueue.maxEvents))
            }
            self.save(stored)
            DeferLinkLogger.debug("EventQueue: \(stored.count) events stored")
        }
    }

    // MARK: - Drain

    /// Returns all queued events and clears the queue.
    /// Call `restore(_:)` with the events that failed to send.
    func drain(completion: @escaping ([DeferLinkEvent]) -> Void) {
        queue.async { [weak self] in
            guard let self = self else { completion([]); return }
            let events = self.load()
            self.save([])
            completion(events)
        }
    }

    /// Re-insert events that could not be sent (prepended, so they are sent first next time).
    func restore(_ events: [DeferLinkEvent]) {
        guard !events.isEmpty else { return }
        queue.async { [weak self] in
            guard let self = self else { return }
            var stored = events + self.load()
            if stored.count > EventQueue.maxEvents {
                stored = Array(stored.suffix(EventQueue.maxEvents))
            }
            self.save(stored)
        }
    }

    // MARK: - Count (approximate, for diagnostics)

    var count: Int {
        queue.sync { load().count }
    }

    // MARK: - Persistence

    private func load() -> [DeferLinkEvent] {
        guard let data = try? Data(contentsOf: fileURL) else { return [] }
        return (try? JSONDecoder().decode([DeferLinkEvent].self, from: data)) ?? []
    }

    private func save(_ events: [DeferLinkEvent]) {
        guard let data = try? JSONEncoder().encode(events) else { return }
        try? data.write(to: fileURL, options: .atomic)
    }
}

// MARK: - DeferLinkEvent: Decodable (needed for queue persistence)
// DeferLinkEvent is already Encodable; add Decodable conformance here.

extension DeferLinkEvent: Decodable {
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        eventId    = try c.decode(String.self,  forKey: .eventId)
        eventName  = try c.decode(String.self,  forKey: .eventName)
        timestamp  = try c.decode(String.self,  forKey: .timestamp)
        sessionId  = try c.decodeIfPresent(String.self,  forKey: .sessionId)
        appUserId  = try c.decodeIfPresent(String.self,  forKey: .appUserId)
        promoId    = try c.decodeIfPresent(String.self,  forKey: .promoId)
        revenue    = try c.decodeIfPresent(Double.self,  forKey: .revenue)
        currency   = (try? c.decode(String.self, forKey: .currency)) ?? "USD"
        properties = try c.decodeIfPresent([String: AnyCodable].self, forKey: .properties)
        platform   = (try? c.decode(String.self, forKey: .platform)) ?? "iOS"
        appVersion = try c.decodeIfPresent(String.self, forKey: .appVersion)
        sdkVersion = (try? c.decode(String.self, forKey: .sdkVersion)) ?? DeferLinkSDKInfo.version
    }
}
