# Premium Data Integration Guide for iOS

This guide shows how to integrate the premium puzzle data API into your iOS app with SwiftUI, including fetching data, parsing responses, and creating beautiful UI components.

---

## Table of Contents

1. [Data Models](#1-data-models)
2. [Network Layer](#2-network-layer)
3. [Range Grid Component](#3-range-grid-component)
4. [Action Breakdown Sheet](#4-action-breakdown-sheet)
5. [EV Comparison View](#5-ev-comparison-view)
6. [Complete Premium View](#6-complete-premium-view)
7. [Styling & Colors](#7-styling--colors)

---

## 1. Data Models

Create Swift models to match the API response structure.

```swift
// Models/PremiumPuzzleData.swift

import Foundation

/// Data for a single hand in the hero range grid
struct HeroHandData: Codable {
    let weight: Double
    let actions: [String: Double]
}

/// Premium analysis data from API
struct PremiumPuzzleData: Codable {
    let puzzleId: String
    let explanations: [String: String]
    let evByAction: [String: Double]
    let actionFrequencies: [String: Double]
    let heroRangeGrid: [String: HeroHandData]?
    let villainRangeGrid: [String: Double]?

    enum CodingKeys: String, CodingKey {
        case puzzleId = "puzzle_id"
        case explanations
        case evByAction = "ev_by_action"
        case actionFrequencies = "action_frequencies"
        case heroRangeGrid = "hero_range_grid"
        case villainRangeGrid = "villain_range_grid"
    }
}

/// Helper to get sorted actions by frequency
extension HeroHandData {
    var sortedActions: [(action: String, frequency: Double)] {
        actions.sorted { $0.value > $1.value }
    }

    var primaryAction: String? {
        sortedActions.first?.action
    }
}

/// Helper to get sorted actions by EV
extension PremiumPuzzleData {
    var actionsSortedByEV: [(action: String, ev: Double)] {
        evByAction.sorted { $0.value > $1.value }
    }

    var bestAction: String? {
        actionsSortedByEV.first?.action
    }
}
```

---

## 2. Network Layer

Create a service to fetch premium data.

```swift
// Services/PremiumDataService.swift

import Foundation

enum PremiumDataError: Error {
    case invalidURL
    case networkError(Error)
    case decodingError(Error)
    case notFound
    case serverError
}

class PremiumDataService {
    private let baseURL = "https://daily-puzzles-api-70941987896.us-central1.run.app"

    func fetchPremiumData(for puzzleId: String) async throws -> PremiumPuzzleData {
        guard let url = URL(string: "\(baseURL)/daily-puzzles/\(puzzleId)/premium") else {
            throw PremiumDataError.invalidURL
        }

        do {
            let (data, response) = try await URLSession.shared.data(from: url)

            guard let httpResponse = response as? HTTPURLResponse else {
                throw PremiumDataError.serverError
            }

            switch httpResponse.statusCode {
            case 200:
                do {
                    let decoder = JSONDecoder()
                    return try decoder.decode(PremiumPuzzleData.self, from: data)
                } catch {
                    throw PremiumDataError.decodingError(error)
                }
            case 404:
                throw PremiumDataError.notFound
            default:
                throw PremiumDataError.serverError
            }
        } catch let error as PremiumDataError {
            throw error
        } catch {
            throw PremiumDataError.networkError(error)
        }
    }
}
```

---

## 3. Range Grid Component

Create a 13x13 range grid that displays hand frequencies with color intensity.

```swift
// Views/Components/RangeGridView.swift

import SwiftUI

struct RangeGridView: View {
    let rangeGrid: [String: HeroHandData]
    let onHandTap: (String, HeroHandData) -> Void

    private let ranks = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"]

    var body: some View {
        VStack(spacing: 0) {
            ForEach(0..<13, id: \.self) { row in
                HStack(spacing: 0) {
                    ForEach(0..<13, id: \.self) { col in
                        RangeGridCell(
                            hand: handLabel(row: row, col: col),
                            data: rangeGrid[handLabel(row: row, col: col)],
                            onTap: onHandTap
                        )
                    }
                }
            }
        }
        .background(Color.gray.opacity(0.1))
        .cornerRadius(8)
    }

    private func handLabel(row: Int, col: Int) -> String {
        let rank1 = ranks[row]
        let rank2 = ranks[col]

        if row == col {
            // Pair (diagonal)
            return "\(rank1)\(rank1)"
        } else if row < col {
            // Suited (above diagonal) - row has higher rank (smaller index)
            return "\(rank1)\(rank2)s"
        } else {
            // Offsuit (below diagonal) - col has higher rank (smaller index)
            return "\(rank2)\(rank1)o"
        }
    }
}

struct RangeGridCell: View {
    let hand: String
    let data: HeroHandData?
    let onTap: (String, HeroHandData) -> Void

    var body: some View {
        Button(action: {
            if let data = data {
                onTap(hand, data)
            }
        }) {
            VStack(spacing: 2) {
                Text(hand)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(textColor)

                if let weight = data?.weight {
                    Text("\(Int(weight * 100))%")
                        .font(.system(size: 8))
                        .foregroundColor(textColor.opacity(0.8))
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .aspectRatio(1, contentMode: .fit)
            .background(backgroundColor)
            .overlay(
                RoundedRectangle(cornerRadius: 2)
                    .stroke(borderColor, lineWidth: borderWidth)
            )
        }
        .buttonStyle(PlainButtonStyle())
        .disabled(data == nil)
    }

    private var backgroundColor: Color {
        guard let weight = data?.weight else {
            return Color.gray.opacity(0.05)
        }

        // Green intensity based on weight
        let intensity = weight
        return Color.green.opacity(intensity * 0.8)
    }

    private var textColor: Color {
        guard let weight = data?.weight else {
            return .gray
        }
        return weight > 0.5 ? .white : .black
    }

    private var borderColor: Color {
        data != nil ? Color.green.opacity(0.3) : Color.gray.opacity(0.2)
    }

    private var borderWidth: CGFloat {
        data != nil ? 1 : 0.5
    }
}

// Preview
struct RangeGridView_Previews: PreviewProvider {
    static var previews: some View {
        RangeGridView(
            rangeGrid: [
                "AA": HeroHandData(weight: 1.0, actions: ["Bet": 0.9, "Check": 0.1]),
                "AKs": HeroHandData(weight: 1.0, actions: ["Bet": 0.8, "Check": 0.2]),
                "AKo": HeroHandData(weight: 0.7, actions: ["Bet": 0.6, "Check": 0.4])
            ],
            onHandTap: { hand, data in
                print("Tapped \(hand)")
            }
        )
        .padding()
    }
}
```

---

## 4. Action Breakdown Sheet

Display action frequencies when user taps a hand in the range grid.

```swift
// Views/Components/HandActionSheet.swift

import SwiftUI

struct HandActionSheet: View {
    let hand: String
    let data: HeroHandData
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationView {
            VStack(spacing: 20) {
                // Hand header
                VStack(spacing: 8) {
                    Text(hand)
                        .font(.system(size: 48, weight: .bold))
                        .foregroundColor(.primary)

                    Text("In range \(Int(data.weight * 100))% of the time")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                }
                .padding(.top, 20)

                Divider()

                // Action frequencies
                VStack(alignment: .leading, spacing: 12) {
                    Text("Optimal Strategy")
                        .font(.headline)
                        .padding(.horizontal)

                    ForEach(data.sortedActions, id: \.action) { item in
                        ActionFrequencyRow(
                            action: item.action,
                            frequency: item.frequency,
                            isPrimary: item.action == data.primaryAction
                        )
                    }
                }

                Spacer()
            }
            .navigationTitle("Hand Details")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") {
                        dismiss()
                    }
                }
            }
        }
    }
}

struct ActionFrequencyRow: View {
    let action: String
    let frequency: Double
    let isPrimary: Bool

    var body: some View {
        VStack(spacing: 6) {
            HStack {
                Text(action)
                    .font(.system(size: 16, weight: isPrimary ? .semibold : .regular))
                Spacer()
                Text("\(Int(frequency * 100))%")
                    .font(.system(size: 16, weight: .medium))
                    .foregroundColor(isPrimary ? .green : .primary)
            }
            .padding(.horizontal)

            // Progress bar
            GeometryReader { geometry in
                ZStack(alignment: .leading) {
                    Rectangle()
                        .fill(Color.gray.opacity(0.2))
                        .frame(height: 8)
                        .cornerRadius(4)

                    Rectangle()
                        .fill(isPrimary ? Color.green : Color.blue)
                        .frame(width: geometry.size.width * frequency, height: 8)
                        .cornerRadius(4)
                }
            }
            .frame(height: 8)
            .padding(.horizontal)
        }
        .padding(.vertical, 4)
    }
}
```

---

## 5. EV Comparison View

Display EV comparison for all actions.

```swift
// Views/Components/EVComparisonView.swift

import SwiftUI

struct EVComparisonView: View {
    let evByAction: [String: Double]
    let actionFrequencies: [String: Double]
    let explanations: [String: String]

    private var sortedActions: [(action: String, ev: Double)] {
        evByAction.sorted { $0.value > $1.value }
    }

    private var bestEV: Double {
        sortedActions.first?.ev ?? 0
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("EV Comparison")
                .font(.headline)

            ForEach(sortedActions, id: \.action) { item in
                EVActionCard(
                    action: item.action,
                    ev: item.ev,
                    maxEV: bestEV,
                    frequency: actionFrequencies[item.action] ?? 0,
                    explanation: explanations[item.action],
                    isBest: item.action == sortedActions.first?.action
                )
            }
        }
        .padding()
    }
}

struct EVActionCard: View {
    let action: String
    let ev: Double
    let maxEV: Double
    let frequency: Double
    let explanation: String?
    let isBest: Bool

    @State private var isExpanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Button(action: {
                withAnimation(.spring(response: 0.3)) {
                    isExpanded.toggle()
                }
            }) {
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text(action)
                                .font(.system(size: 17, weight: .semibold))

                            if isBest {
                                Image(systemName: "star.fill")
                                    .font(.system(size: 12))
                                    .foregroundColor(.yellow)
                            }
                        }

                        HStack(spacing: 12) {
                            Text("EV: \(ev, specifier: "%.2f") bb")
                                .font(.system(size: 14))
                                .foregroundColor(.secondary)

                            Text("GTO: \(Int(frequency * 100))%")
                                .font(.system(size: 14))
                                .foregroundColor(.blue)
                        }
                    }

                    Spacer()

                    Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(.secondary)
                }
            }
            .buttonStyle(PlainButtonStyle())

            // EV bar
            GeometryReader { geometry in
                ZStack(alignment: .leading) {
                    Rectangle()
                        .fill(Color.gray.opacity(0.15))
                        .frame(height: 6)
                        .cornerRadius(3)

                    Rectangle()
                        .fill(evColor)
                        .frame(width: geometry.size.width * (ev / maxEV), height: 6)
                        .cornerRadius(3)
                }
            }
            .frame(height: 6)

            // Explanation (expandable)
            if isExpanded, let explanation = explanation {
                Text(explanation)
                    .font(.system(size: 14))
                    .foregroundColor(.secondary)
                    .padding(.top, 4)
                    .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
        .padding()
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(isBest ? Color.green.opacity(0.05) : Color.gray.opacity(0.05))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(isBest ? Color.green.opacity(0.3) : Color.clear, lineWidth: 2)
        )
    }

    private var evColor: Color {
        let ratio = ev / maxEV
        if ratio > 0.95 {
            return .green
        } else if ratio > 0.85 {
            return .blue
        } else {
            return .orange
        }
    }
}
```

---

## 6. Complete Premium View

Combine all components into a complete premium analysis view.

```swift
// Views/PremiumAnalysisView.swift

import SwiftUI

struct PremiumAnalysisView: View {
    let puzzleId: String

    @StateObject private var viewModel = PremiumAnalysisViewModel()
    @State private var selectedHand: (hand: String, data: HeroHandData)?
    @State private var selectedTab = 0

    var body: some View {
        Group {
            switch viewModel.state {
            case .loading:
                ProgressView("Loading premium data...")

            case .loaded(let data):
                ScrollView {
                    VStack(spacing: 24) {
                        // Tab selector
                        Picker("Analysis Type", selection: $selectedTab) {
                            Text("Range Grid").tag(0)
                            Text("EV Analysis").tag(1)
                        }
                        .pickerStyle(SegmentedPickerStyle())
                        .padding(.horizontal)

                        if selectedTab == 0 {
                            rangeGridSection(data: data)
                        } else {
                            evAnalysisSection(data: data)
                        }
                    }
                    .padding(.vertical)
                }

            case .error(let error):
                VStack(spacing: 16) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.system(size: 48))
                        .foregroundColor(.orange)

                    Text("Failed to load premium data")
                        .font(.headline)

                    Text(error.localizedDescription)
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal)

                    Button("Retry") {
                        Task {
                            await viewModel.loadPremiumData(puzzleId: puzzleId)
                        }
                    }
                    .buttonStyle(.borderedProminent)
                }
            }
        }
        .navigationTitle("Premium Analysis")
        .navigationBarTitleDisplayMode(.inline)
        .sheet(item: $selectedHand) { item in
            HandActionSheet(hand: item.hand, data: item.data)
        }
        .task {
            await viewModel.loadPremiumData(puzzleId: puzzleId)
        }
    }

    @ViewBuilder
    private func rangeGridSection(data: PremiumPuzzleData) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            VStack(alignment: .leading, spacing: 8) {
                Text("Hero Range")
                    .font(.title2)
                    .fontWeight(.bold)
                    .padding(.horizontal)

                Text("Tap any hand to see optimal strategy")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                    .padding(.horizontal)
            }

            if let heroGrid = data.heroRangeGrid {
                RangeGridView(rangeGrid: heroGrid) { hand, handData in
                    selectedHand = (hand, handData)
                }
                .padding(.horizontal)

                // Legend
                HStack(spacing: 16) {
                    ForEach([
                        ("0-25%", 0.125),
                        ("25-50%", 0.375),
                        ("50-75%", 0.625),
                        ("75-100%", 0.875)
                    ], id: \.0) { label, intensity in
                        HStack(spacing: 4) {
                            RoundedRectangle(cornerRadius: 4)
                                .fill(Color.green.opacity(intensity * 0.8))
                                .frame(width: 20, height: 20)
                            Text(label)
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                }
                .padding(.horizontal)
                .padding(.top, 8)
            } else {
                Text("Range data not available")
                    .foregroundColor(.secondary)
                    .padding()
            }
        }
    }

    @ViewBuilder
    private func evAnalysisSection(data: PremiumPuzzleData) -> some View {
        EVComparisonView(
            evByAction: data.evByAction,
            actionFrequencies: data.actionFrequencies,
            explanations: data.explanations
        )
    }
}

// ViewModel
@MainActor
class PremiumAnalysisViewModel: ObservableObject {
    enum State {
        case loading
        case loaded(PremiumPuzzleData)
        case error(Error)
    }

    @Published var state: State = .loading

    private let service = PremiumDataService()

    func loadPremiumData(puzzleId: String) async {
        state = .loading

        do {
            let data = try await service.fetchPremiumData(for: puzzleId)
            state = .loaded(data)
        } catch {
            state = .error(error)
        }
    }
}

// Make tuple Identifiable for sheet
extension PremiumAnalysisView {
    struct HandIdentifiable: Identifiable {
        let id = UUID()
        let hand: String
        let data: HeroHandData
    }
}

extension Binding where Value == (hand: String, data: HeroHandData)? {
    var identifiable: Binding<PremiumAnalysisView.HandIdentifiable?> {
        Binding<PremiumAnalysisView.HandIdentifiable?>(
            get: {
                guard let value = self.wrappedValue else { return nil }
                return PremiumAnalysisView.HandIdentifiable(hand: value.hand, data: value.data)
            },
            set: { _ in
                self.wrappedValue = nil
            }
        )
    }
}
```

---

## 7. Styling & Colors

Create a color scheme for consistent theming.

```swift
// Utils/PremiumColors.swift

import SwiftUI

extension Color {
    // Premium feature colors
    static let premiumGold = Color(red: 255/255, green: 215/255, blue: 0/255)
    static let premiumGreen = Color(red: 76/255, green: 175/255, blue: 80/255)
    static let premiumBlue = Color(red: 33/255, green: 150/255, blue: 243/255)

    // Range grid colors
    static let rangeHigh = Color.green
    static let rangeMedium = Color.blue
    static let rangeLow = Color.orange
    static let rangeNone = Color.gray.opacity(0.1)

    // EV comparison
    static let evBest = Color.green
    static let evGood = Color.blue
    static let evOkay = Color.orange
    static let evBad = Color.red
}

// Custom button style for premium features
struct PremiumButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .padding()
            .background(
                LinearGradient(
                    colors: [Color.premiumGold, Color.yellow],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            )
            .foregroundColor(.black)
            .cornerRadius(12)
            .scaleEffect(configuration.isPressed ? 0.95 : 1.0)
            .animation(.spring(response: 0.3), value: configuration.isPressed)
    }
}
```

---

## Usage Example

Here's how to integrate the premium view into your app:

```swift
// In your puzzle detail view
import SwiftUI

struct PuzzleDetailView: View {
    let puzzle: Puzzle
    @State private var showPremiumAnalysis = false

    var body: some View {
        VStack {
            // Regular puzzle UI

            // Premium unlock button
            Button(action: {
                showPremiumAnalysis = true
            }) {
                HStack {
                    Image(systemName: "crown.fill")
                    Text("View Premium Analysis")
                }
            }
            .buttonStyle(PremiumButtonStyle())
            .padding()
        }
        .sheet(isPresented: $showPremiumAnalysis) {
            NavigationView {
                PremiumAnalysisView(puzzleId: puzzle.id)
            }
        }
    }
}
```

---

## Performance Tips

1. **Cache Premium Data**: Store fetched data locally to avoid repeated API calls
```swift
class PremiumDataCache {
    static let shared = PremiumDataCache()
    private var cache: [String: PremiumPuzzleData] = [:]

    func get(_ puzzleId: String) -> PremiumPuzzleData? {
        cache[puzzleId]
    }

    func set(_ data: PremiumPuzzleData, for puzzleId: String) {
        cache[puzzleId] = data
    }
}
```

2. **Lazy Loading**: Only load premium data when user actually opens the premium view

3. **Image Assets**: Use SF Symbols for icons to keep app size small

4. **Animations**: Use `.animation(.spring())` for smooth, natural transitions

---

## Testing

Example unit test for data parsing:

```swift
import XCTest
@testable import YourApp

class PremiumDataTests: XCTestCase {
    func testPremiumDataDecoding() throws {
        let json = """
        {
            "puzzle_id": "test-123",
            "explanations": {"Check": "Test explanation"},
            "ev_by_action": {"Check": 1.5},
            "action_frequencies": {"Check": 0.5},
            "hero_range_grid": {
                "AA": {"weight": 1.0, "actions": {"Bet": 0.9}}
            },
            "villain_range_grid": {"AKs": 0.8}
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        let data = try decoder.decode(PremiumPuzzleData.self, from: json)

        XCTAssertEqual(data.puzzleId, "test-123")
        XCTAssertEqual(data.heroRangeGrid?["AA"]?.weight, 1.0)
    }
}
```

---

## Accessibility

Ensure premium features are accessible:

```swift
RangeGridCell(...)
    .accessibilityLabel("\(hand) in range \(Int(data.weight * 100))%")
    .accessibilityHint("Tap to see optimal strategy")
    .accessibilityAddTraits(data != nil ? .isButton : [])
```

---

## Summary

This guide provides:
- ✅ Complete data models matching the API
- ✅ Network layer with error handling
- ✅ Beautiful 13x13 range grid component
- ✅ Interactive action breakdown sheets
- ✅ EV comparison with visual indicators
- ✅ Complete premium analysis view
- ✅ Consistent styling and colors
- ✅ Performance optimization tips

The UI is designed to be:
- **Intuitive**: Tap any hand to see strategy
- **Visual**: Color-coded range grid shows frequency at a glance
- **Educational**: Explanations help users understand GTO strategy
- **Premium**: Gold accents and smooth animations create premium feel
