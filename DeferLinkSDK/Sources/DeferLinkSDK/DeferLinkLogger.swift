// DeferLinkLogger.swift
// DeferLinkSDK
//
// Простой внутренний логгер.
// Активируется через DeferLinkConfiguration(debugLogging: true).

import Foundation
import os.log

enum DeferLinkLogger {

    static var isEnabled = false

    private static let logger = Logger(
        subsystem: "com.deferlink.sdk",
        category:  "DeferLink"
    )

    static func debug(_ message: String) {
        guard isEnabled else { return }
        logger.debug("[DeferLink] \(message, privacy: .public)")
    }

    static func warning(_ message: String) {
        logger.warning("[DeferLink] ⚠️ \(message, privacy: .public)")
    }

    static func error(_ message: String) {
        logger.error("[DeferLink] ❌ \(message, privacy: .public)")
    }
}
