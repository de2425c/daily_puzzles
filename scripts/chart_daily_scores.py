#!/usr/bin/env python3
"""
Create a chart of average daily score over time.

Usage:
    uv run --with matplotlib --with pandas python scripts/chart_daily_scores.py
"""

import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path


def main():
    # Load the CSV
    csv_path = Path(__file__).parent.parent / "daily10_completions_export.csv"
    df = pd.read_csv(csv_path)

    # Convert scheduled_date to datetime
    df['scheduled_date'] = pd.to_datetime(df['scheduled_date'])

    # Group by date and calculate average score percentage
    daily_stats = df.groupby('scheduled_date').agg({
        'score_percentage': 'mean',
        'user_id': 'count'  # number of completions
    }).rename(columns={'user_id': 'completions'})

    daily_stats = daily_stats.reset_index()

    # Create the chart
    fig, ax1 = plt.subplots(figsize=(14, 6))

    # Plot average score
    color = '#2563eb'
    ax1.set_xlabel('Date', fontsize=12)
    ax1.set_ylabel('Average Score (%)', color=color, fontsize=12)
    line1 = ax1.plot(daily_stats['scheduled_date'], daily_stats['score_percentage'],
                      color=color, linewidth=2, marker='o', markersize=6, label='Avg Score')
    ax1.tick_params(axis='y', labelcolor=color)
    ax1.set_ylim(50, 100)

    # Add a second y-axis for number of completions
    ax2 = ax1.twinx()
    color2 = '#10b981'
    ax2.set_ylabel('Number of Completions', color=color2, fontsize=12)
    bars = ax2.bar(daily_stats['scheduled_date'], daily_stats['completions'],
                   alpha=0.3, color=color2, width=0.8, label='Completions')
    ax2.tick_params(axis='y', labelcolor=color2)

    # Add value labels on the line
    for x, y in zip(daily_stats['scheduled_date'], daily_stats['score_percentage']):
        ax1.annotate(f'{y:.1f}%', (x, y), textcoords="offset points",
                     xytext=(0, 8), ha='center', fontsize=8, color=color)

    # Title and formatting
    plt.title('Daily 10 - Average Score by Day', fontsize=14, fontweight='bold', pad=20)
    fig.tight_layout()

    # Rotate x-axis labels
    plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45, ha='right')

    # Add legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + [bars], labels1 + ['Completions'], loc='upper left')

    # Add grid
    ax1.grid(True, alpha=0.3, linestyle='--')

    # Save the chart
    output_path = Path(__file__).parent.parent / "daily10_scores_chart.png"
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    print(f"Chart saved to: {output_path}")

    # Also print the data
    print("\nDaily Statistics:")
    print("-" * 50)
    for _, row in daily_stats.iterrows():
        print(f"{row['scheduled_date'].strftime('%Y-%m-%d')}: "
              f"Avg Score = {row['score_percentage']:.1f}%, "
              f"Completions = {int(row['completions'])}")

    print(f"\nOverall Average: {daily_stats['score_percentage'].mean():.1f}%")
    print(f"Total Completions: {int(daily_stats['completions'].sum())}")


if __name__ == "__main__":
    main()
