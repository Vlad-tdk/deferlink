// EventTracker.swift
// DeferLinkSDK
//
// Batching + retry logic for event delivery.
//
// Strategy:
//   • Events are buffered in memory (up to batchSize).
//   • The buffer is flushed either:
//       – when it reaches batchSize, OR
//       – on a periodic timer (every flushInterval seconds).
//   • Failed batches are re-queued to the persistent EventQueue.
//   • On app foreground, the persistent queue is flushed first.

import Foundation
import UIKit

// MARK: - EventTracker

@MainActor
final class EventTracker {

    // MARK: - Configuration

    struct Config {
        /// Max events in one HTTP batch request.
        var batchSize:      Int    = 20
        /// Seconds between automatic flushes.
        var flushInterval:  Double = 15.0
        /// Max retry attempts before dropping a batch.
        var maxRetries:     Int    = 3
    }

    // MARK: - State

    private let client:       DeferLinkClient
    private let queue:        EventQueue
    private var cfg:          Config

    /// Attribution context injected by DeferLink after resolve.
    var sessionId:  String?
    var promoId:    String?
    /// App-level user identifier (set via DeferLink.shared.setUserId).
    var appUserId:  String?

    /// In-memory buffer — flushed on timer or when full.
    private var buffer: [DeferLinkEvent] = []

    private var flushTimer: Timer?
    private var retryCount: [String: Int] = [:]   // eventId → retry count (not used here; batch-level)

    // MARK: - Init

    init(client: DeferLinkClient, queue: EventQueue, config: Config = Config()) {
        self.client = client
        self.queue  = queue
        self.cfg    = config

        scheduleFlushTimer()
        observeAppLifecycle()
    }

    // MARK: - Public API

    /// Enqueue a single event.  Attribution context is stamped automatically.
    func track(_ event: DeferLinkEvent) {
        var ev = event
        if ev.sessionId  == nil { ev.sessionId  = sessionId  }
        if ev.promoId    == nil { ev.promoId    = promoId    }
        if ev.appUserId  == nil { ev.appUserId  = appUserId  }

        buffer.append(ev)
        DeferLinkLogger.debug("EventTracker: buffered '\(ev.eventName)' (buffer=\(buffer.count))")

        if buffer.count >= cfg.batchSize {
            flushBuffer()
        }
    }

    /// Force flush all buffered events immediately (e.g. on app background).
    func flush() {
        flushBuffer()
        flushPersistentQueue()
    }

    // MARK: - Flush logic

    private func flushBuffer() {
        guard !buffer.isEmpty else { return }
        let batch = buffer
        buffer = []
        send(batch: batch, attempt: 0)
    }

    private func flushPersistentQueue() {
        queue.drain { [weak self] events in
            guard let self = self, !events.isEmpty else { return }
            DeferLinkLogger.debug("EventTracker: flushing \(events.count) persisted events")
            Task { @MainActor in
                self.send(batch: events, attempt: 0)
            }
        }
    }

    // MARK: - Network send

    private func send(batch: [DeferLinkEvent], attempt: Int) {
        guard !batch.isEmpty else { return }
        Task { @MainActor [weak self] in
            guard let self = self else { return }
            do {
                let result = try await self.client.sendEvents(batch)
                DeferLinkLogger.debug(
                    "EventTracker: ✅ sent \(batch.count) events — inserted=\(result.inserted)"
                )
            } catch {
                DeferLinkLogger.warning("EventTracker: send failed (attempt \(attempt+1)): \(error.localizedDescription)")
                if attempt + 1 < self.cfg.maxRetries {
                    // Exponential back-off: 2^attempt seconds, capped at 60s
                    let delay = min(pow(2.0, Double(attempt)), 60.0)
                    try? await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
                    self.send(batch: batch, attempt: attempt + 1)
                } else {
                    // Give up for now — persist for next session
                    DeferLinkLogger.warning("EventTracker: max retries reached — persisting \(batch.count) events")
                    self.queue.enqueue(batch)
                }
            }
        }
    }

    // MARK: - Timer

    private func scheduleFlushTimer() {
        flushTimer?.invalidate()
        flushTimer = Timer.scheduledTimer(withTimeInterval: cfg.flushInterval, repeats: true) { [weak self] _ in
            Task { @MainActor [weak self] in
                self?.flushBuffer()
            }
        }
    }

    // MARK: - App lifecycle

    private func observeAppLifecycle() {
        NotificationCenter.default.addObserver(
            forName: UIApplication.willResignActiveNotification,
            object:  nil,
            queue:   .main
        ) { [weak self] _ in
            Task { @MainActor [weak self] in
                DeferLinkLogger.debug("EventTracker: app going background — flushing")
                self?.flush()
            }
        }

        NotificationCenter.default.addObserver(
            forName: UIApplication.didBecomeActiveNotification,
            object:  nil,
            queue:   .main
        ) { [weak self] _ in
            Task { @MainActor [weak self] in
                DeferLinkLogger.debug("EventTracker: app became active — flushing persisted queue")
                self?.flushPersistentQueue()
            }
        }
    }
}

// MARK: - Server response model

struct EventBatchResponse: Decodable {
    let success:   Bool
    let inserted:  Int
    let duplicate: Int
    let failed:    Int
}
