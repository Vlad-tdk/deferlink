//
//  SKANManager.swift
//  DeferLinkSDK
//
//  Coordinates:
//    1. Fetching SKANConfig from the backend (with cached fallback)
//    2. Tracking sessions, revenue and "core actions" inside the SKAN
//       conversion window (default 48 hours after install)
//    3. Re-computing the 6-bit conversion value and submitting it to
//       Apple via SKAdNetwork.updatePostbackConversionValue(...)
//
//  All public methods are @MainActor — call from the main thread (UIKit
//  app delegate hooks etc.). The session tracker observes UIScene /
//  UIApplication lifecycle automatically.
//

import Foundation

#if canImport(UIKit)
import UIKit
#endif

#if canImport(StoreKit)
import StoreKit
#endif

@MainActor
public final class SKANManager {

    // MARK: - Public API

    /// Mark a meaningful in-app event (e.g. registration_qualified, key feature
    /// used). Increments coreActionCount which feeds engagement tier.
    public func markCoreAction() {
        let state = stateStore.update { $0.coreActionCount += 1 }
        Task { await updateConversionValue(state: state, isConversion: false) }
    }

    /// Record revenue from an in-app purchase or subscription.
    public func recordRevenue(_ usd: Double, currency: String = "USD") {
        guard usd > 0 else { return }
        let usdValue = currency == "USD" ? usd : usd  // (FX is server-side)
        let state = stateStore.update { $0.revenueUSD += usdValue }
        Task { await updateConversionValue(state: state, isConversion: true) }
    }

    /// Force a recompute + re-submit (without changing inputs).
    public func refresh() {
        let state = stateStore.load()
        Task { await updateConversionValue(state: state, isConversion: false) }
    }

    /// Hard-reset state — useful in test harnesses; do NOT call in prod.
    public func resetState() {
        stateStore.reset()
    }

    // MARK: - Internal

    private let appId:        String
    private let client:       DeferLinkClient
    private let stateStore    = SKANStateStore()
    private var config:       SKANConfig
    private var lifecycleHooked = false
    private var sessionStartedAt: Date?

    init(appId: String, client: DeferLinkClient) {
        self.appId  = appId
        self.client = client
        self.config = SKANConfig.bundledDefaults(appId: appId)

        // Register install date if first launch
        _ = stateStore.load()

        Task { await self.refreshConfig() }
        hookLifecycle()
    }

    // MARK: - Config refresh

    public func refreshConfig() async {
        do {
            let fetched = try await client.fetchSKANConfig(appId: appId)
            self.config = fetched
            DeferLinkLogger.debug("SKANManager: config refreshed (schema=\(fetched.schemaName))")
        } catch {
            DeferLinkLogger.debug("SKANManager: config fetch failed (\(error)); using defaults")
        }
    }

    // MARK: - Session tracking

    private func hookLifecycle() {
        guard !lifecycleHooked else { return }
        lifecycleHooked = true

        #if canImport(UIKit)
        let nc = NotificationCenter.default

        nc.addObserver(forName: UIApplication.didBecomeActiveNotification,
                       object: nil, queue: .main) { [weak self] _ in
            Task { @MainActor in self?.handleSessionStart() }
        }

        nc.addObserver(forName: UIApplication.willResignActiveNotification,
                       object: nil, queue: .main) { [weak self] _ in
            Task { @MainActor in self?.handleSessionEnd() }
        }
        #endif

        // Fire one synthetic session start for the launch
        handleSessionStart()
    }

    private func handleSessionStart() {
        sessionStartedAt = Date()
        let state = stateStore.update { s in
            let now = Date()
            s.sessionCount += 1

            // retention flags
            let installDay  = Calendar.current.startOfDay(for: s.installDate)
            let today       = Calendar.current.startOfDay(for: now)
            let daysSince   = Calendar.current.dateComponents([.day],
                                                              from: installDay,
                                                              to: today).day ?? 0
            if daysSince >= 1 { s.returnedNextDay = true }
            if daysSince >= 2 { s.retainedDayTwo  = true }

            s.lastSessionDate = now
        }
        Task { await updateConversionValue(state: state, isConversion: false) }
    }

    private func handleSessionEnd() {
        guard let started = sessionStartedAt else { return }
        let elapsed = Date().timeIntervalSince(started)
        sessionStartedAt = nil
        guard elapsed > 0 else { return }

        let state = stateStore.update { $0.totalSessionSeconds += elapsed }
        Task { await updateConversionValue(state: state, isConversion: false) }
    }

    // MARK: - CV submission

    private func updateConversionValue(state: SKANState, isConversion: Bool) async {
        // Skip if past the conversion window
        let windowEnd = state.installDate.addingTimeInterval(
            TimeInterval(config.conversionWindowHours) * 3600
        )
        guard Date() < windowEnd else { return }

        let cv = CVEncoder.computeCV(
            revenueUSD:      state.revenueUSD,
            sessions:        state.sessionCount,
            totalSeconds:    state.totalSessionSeconds,
            coreActions:     state.coreActionCount,
            returnedNextDay: state.returnedNextDay,
            retainedDayTwo:  state.retainedDayTwo,
            isConversion:    isConversion || state.revenueUSD > 0,
            config:          config
        )

        // Apple's rule: CV must be monotonically non-decreasing within
        // the conversion window for the postback to fire.
        guard cv >= state.lastCV else {
            DeferLinkLogger.debug("SKANManager: skip CV=\(cv) (not greater than last=\(state.lastCV))")
            return
        }

        let submitted = await submit(cv: cv)
        guard submitted else {
            DeferLinkLogger.debug("SKANManager: CV=\(cv) not persisted because StoreKit update failed")
            return
        }

        _ = stateStore.update { $0.lastCV = cv }
        DeferLinkLogger.debug("SKANManager: submitted CV=\(cv)")
    }

    private func submit(cv: Int) async -> Bool {
        #if canImport(StoreKit)
        if #available(iOS 16.1, *) {
            do {
                let coarse: SKAdNetwork.CoarseConversionValue
                switch cv {
                case 0...20:  coarse = .low
                case 21...41: coarse = .medium
                default:       coarse = .high
                }
                try await SKAdNetwork.updatePostbackConversionValue(
                    cv,
                    coarseValue: coarse,
                    lockWindow:  false
                )
                return true
            } catch {
                DeferLinkLogger.debug("SKANManager: SKAN v4 update failed (\(error)); falling back")
            }
        }

        if #available(iOS 15.4, *) {
            return await withCheckedContinuation { continuation in
                SKAdNetwork.updatePostbackConversionValue(cv) { error in
                    if let error = error {
                        DeferLinkLogger.debug("SKANManager: SKAN v3 update error: \(error)")
                        continuation.resume(returning: false)
                    } else {
                        continuation.resume(returning: true)
                    }
                }
            }
        } else if #available(iOS 14.0, *) {
            SKAdNetwork.updateConversionValue(cv)
            return true
        }
        #endif

        return false
    }
}
