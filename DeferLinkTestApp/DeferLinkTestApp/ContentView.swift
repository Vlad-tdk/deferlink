//
//  ContentView.swift
//  DeferLinkTestApp
//
//  Created by Vladimir Martemianov on 3. 6. 2025..
//

import SwiftUI

struct ContentView: View {
    @StateObject private var deferLinkService = DeferLinkService()
    @StateObject private var networkManager = NetworkManager.shared
    
    var body: some View {
        TabView {
            DeepLinkTestView()
                .environmentObject(deferLinkService)
                .environmentObject(networkManager)
                .tabItem {
                    Image(systemName: "link")
                    Text("Тесты")
                }
            
            SettingsView()
                .environmentObject(networkManager)
                .tabItem {
                    Image(systemName: "gear")
                    Text("Настройки")
                }
            
            DeviceInfoView()
                .tabItem {
                    Image(systemName: "info.circle")
                    Text("Устройство")
                }
        }
    }
}

struct ContentView_Previews: PreviewProvider {
    static var previews: some View {
        ContentView()
    }
}
