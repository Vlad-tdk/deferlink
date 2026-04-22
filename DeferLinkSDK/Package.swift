// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "DeferLinkSDK",
    platforms: [
        .iOS(.v15)
    ],
    products: [
        .library(
            name: "DeferLinkSDK",
            targets: ["DeferLinkSDK"]
        )
    ],
    targets: [
        .target(
            name: "DeferLinkSDK",
            path: "Sources/DeferLinkSDK",
            swiftSettings: [
                .enableExperimentalFeature("StrictConcurrency")
            ]
        ),
        .testTarget(
            name: "DeferLinkSDKTests",
            dependencies: ["DeferLinkSDK"],
            path: "Tests/DeferLinkSDKTests"
        )
    ]
)
