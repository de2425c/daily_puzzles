# Premium Data API for iOS App

## Endpoint

```
GET https://daily-puzzles-api-70941987896.us-central1.run.app/daily-puzzles/{puzzle_id}/premium
```

## Description

Returns premium analysis data for a puzzle. Call this endpoint when a user with premium subscription wants to see advanced analysis (explanations, EVs, GTO frequencies, range grids with optimal actions).

## Request

- **Method:** GET
- **Path Parameter:** `puzzle_id` - The puzzle's UUID from `new_daily_puzzles` collection

## Response

```json
{
  "puzzle_id": "0c992ddf-399e-4f10-930a-800733bcfb84",
  "explanations": {
    "Check": "Explanation for checking...",
    "Bet 1.6bb": "Explanation for betting 1.6bb...",
    "Bet 6.2bb": "Explanation for betting 6.2bb..."
  },
  "ev_by_action": {
    "Check": 1.675,
    "Bet 1.6bb": 1.709,
    "Bet 3.8bb": 1.665,
    "Bet 6.2bb": 1.570
  },
  "action_frequencies": {
    "Check": 0.000005,
    "Bet 1.6bb": 0.996,
    "Bet 3.8bb": 0.003,
    "Bet 6.2bb": 0.0003
  },
  "hero_range_grid": {
    "AA": {
      "weight": 1.0,
      "actions": {
        "Bet 1.6bb": 0.85,
        "Bet 3.8bb": 0.10,
        "Check": 0.05
      }
    },
    "AKs": {
      "weight": 1.0,
      "actions": {
        "Bet 1.6bb": 0.92,
        "Bet 3.8bb": 0.08
      }
    },
    "22": {
      "weight": 0.515,
      "actions": {
        "Bet 1.6bb": 0.863,
        "Bet 3.8bb": 0.051,
        "Bet 6.2bb": 0.08,
        "Check": 0.006
      }
    }
  },
  "villain_range_grid": {
    "AA": 0.0,
    "AKs": 0.0,
    "AQs": 0.519,
    "22": 0.166
  }
}
```

## Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `puzzle_id` | string | The puzzle UUID |
| `explanations` | object | Per-action explanations. Keys are action names (e.g., "Check", "Bet 1.6bb") |
| `ev_by_action` | object | Expected value in big blinds for each action |
| `action_frequencies` | object | GTO frequency (0-1) for each action (overall for hero's range) |
| `hero_range_grid` | object | Hero's range with optimal actions per hand (see below) |
| `villain_range_grid` | object | Villain's range as simple weights (0-1) |

## Hero Range Grid Format

Each hand in `hero_range_grid` contains:
- `weight`: Frequency of hand in range (0-1)
- `actions`: Optimal action frequencies for that specific hand

```json
"AKs": {
  "weight": 1.0,           // 100% of AKs combos are in hero's range
  "actions": {
    "Bet 1.6bb": 0.92,     // Bet small 92% of the time with AKs
    "Bet 3.8bb": 0.08      // Bet medium 8% of the time
  }
}
```

This allows displaying:
1. A colored 13x13 range grid (using `weight` for color intensity)
2. Action breakdown when user taps a specific hand

## Villain Range Grid Format

Simple weights (0-1) for each hand:
```json
"villain_range_grid": {
  "AQs": 0.519,   // 51.9% of AQs combos in villain's range
  "22": 0.166    // 16.6% of 22 combos
}
```

## Hand Notation

Standard poker hand notation:
- Pairs: `"AA"`, `"KK"`, `"22"` (6 combos each)
- Suited: `"AKs"`, `"T9s"` (4 combos each)
- Offsuit: `"AKo"`, `"T9o"` (12 combos each)

Only hands with frequency > 0.001 are included.

## Error Responses

| Status | Description |
|--------|-------------|
| 404 | Puzzle not found |
| 500 | Server error (sim not found, tree parsing failed) |

## Example Usage (Swift)

```swift
struct HeroHandData: Codable {
    let weight: Double
    let actions: [String: Double]
}

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

func fetchPremiumData(puzzleId: String) async throws -> PremiumPuzzleData {
    let url = URL(string: "https://daily-puzzles-api-70941987896.us-central1.run.app/daily-puzzles/\(puzzleId)/premium")!
    let (data, _) = try await URLSession.shared.data(from: url)
    return try JSONDecoder().decode(PremiumPuzzleData.self, from: data)
}

// Example: Display action breakdown for a hand
if let handData = premiumData.heroRangeGrid?["AKs"] {
    print("AKs is in range \(handData.weight * 100)% of the time")
    for (action, freq) in handData.actions.sorted(by: { $0.value > $1.value }) {
        print("  \(action): \(Int(freq * 100))%")
    }
}
```

## Notes

- Range grids may be `null` if the solver sim is not found or tree parsing fails
- Hero grid includes optimal actions for each hand; villain grid is static weights only
- Action frequencies in hero grid are specific to that hand (not the overall range frequency)
