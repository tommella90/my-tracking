import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import date, timedelta
import streamlit as st

st.set_page_config(page_title="Energy Tracker", layout="wide")

# Get today's date early so it's available throughout
today = date.today()

# --- Color Configuration (Modify all colors here) ---
# Chart colors
COLORS = {
    'spine': '#333333',
    'grid_alpha': 0.3,
    'exertion_dot': '#8B0000',
    'exertion_dot_edge': 'black',
    'band_alpha': 0.2,
}

# Horizontal band colors (one for each integer interval: 0-1, 1-2, 2-3, etc.)
# Add/remove colors as needed for your y-axis range
BAND_COLORS = [
    "#410b0b",  # 0-1
    "#5e0f0f",  # 1-2
    "#811616",  # 2-3
    "#A52727",  # 3-4
    "#CB702F",  # 4-5
    "#bab52a",  # 5-6
    "#68d187",  # 6-7
    "#56aa6f",  # 7-8
    "#5660aa",  # 8-9
    "#2411b8",  # 9-10
]

# Color Palette (Managua)
cmap = plt.colormaps['copper']

def get_spread_colors(n):
    """Pick n colors from managua colormap, spreading from extremes inward."""
    if n == 1:
        return [cmap(0.0)]
    if n == 2:
        return [cmap(0.0), cmap(1.0)]
    # For n>=3: start with extremes, then fill from the middle outward
    # Generate candidate positions: 0, 1, 0.5, 0.25, 0.75, 0.125, 0.625, 0.375, 0.875, ...
    positions = []
    for level in range(20):  # enough levels for reasonable n
        if level == 0:
            positions.extend([0.0, 1.0])
        elif level == 1:
            positions.append(0.5)
        else:
            # subdivide existing intervals, pick midpoints
            new_positions = []
            sorted_pos = sorted(positions)
            for i in range(len(sorted_pos) - 1):
                new_positions.append((sorted_pos[i] + sorted_pos[i + 1]) / 2)
            positions.extend(new_positions)
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for p in positions:
        key = round(p, 10)
        if key not in seen:
            seen.add(key)
            unique.append(p)
        if len(unique) >= n:
            break
    return [cmap(p) for p in unique[:n]]

# --- Data Loading ---
@st.cache_data
def load_data():
    df = pd.read_excel('data/otherData/energy_tracker.ods', engine='odf')
    columns = ['date', 'stress_level(1-5)', 'sleep_hours', 'physical activity', 'focus', 'cognitive-usage', 'hyperactive-brain', 'total activity', 'social activity', 'POTS 0-5', 'mood', 'energy', 'exertion', 'fatigue', 'activity', 'sympthoms', 'poop1', 'poop2', 'poop3', 'supplements', 'notes1', 'notes 2', 'breakfast', 'lunch', 'snack1', 'dinner', 'snack2', 'fruit', 'stomach issues']
    df = df[columns]
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    # Convert numeric columns that might have string values
    numeric_cols = ['physical activity', 'total activity', 'activity']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.dropna(subset=['date']).sort_values('date').reset_index(drop=True)
    return df

df = load_data()

# --- CSV Download ---
st.download_button(
    label="⬇️ Download CSV",
    data=df.to_csv(index=False).encode('utf-8'),
    file_name="energy_tracker.csv",
    mime="text/csv"
)

# --- Table (last 5 days) ---
st.subheader("Last 5 days")
# Get last 5 days before today (not including today)
today_date = pd.to_datetime(today)
start_date = today_date - timedelta(days=5)
end_date = today_date - timedelta(days=1)
last_5_days = df[(df['date'] >= start_date) & (df['date'] <= end_date)]
st.dataframe(last_5_days, use_container_width=True)

# --- Chart Section ---
st.subheader("Trends")

# Date range picker (default: 3 months)
three_months_ago = today - timedelta(days=90)

date_range = st.date_input(
    "Date range",
    value=(three_months_ago, today),
    min_value=df['date'].min().date(),
    max_value=today
)

if len(date_range) == 2:
    start, end = date_range
    mask = (df['date'].dt.date >= start) & (df['date'].dt.date <= end)
    filtered_df = df[mask]
else:
    filtered_df = df

# Variable selection as pills (always visible)
chart_vars = ['stress_level(1-5)', 'sleep_hours', 'physical activity', 'focus', 'cognitive-usage', 'total activity', 'social activity', 'POTS 0-5', 'mood', 'energy', 'fatigue', 'activity']

bar_vars = {'stress_level(1-5)', 'POTS 0-5', 'physical activity'}

default_vars = ['fatigue', 'energy']

selected_vars = st.pills(
    "Variables to display",
    options=chart_vars,
    selection_mode="multi",
    default=default_vars
)

if selected_vars:
    fig, ax = plt.subplots(figsize=(14, 6))

    # Remove all splines EXCEPT bottom
    for spine_name, spine in ax.spines.items():
        if spine_name == 'bottom':
            spine.set_visible(True)
            spine.set_linewidth(0.8)
            spine.set_color(COLORS['spine'])
        else:
            spine.set_visible(False)

    # Horizontal bands with different colors (0-1, 1-2, 2-3, etc.)
    y_max = 10
    for band_idx, color in enumerate(BAND_COLORS):
        y_start = band_idx
        y_end = band_idx + 1
        if y_start >= y_max:
            break
        if y_end > y_max:
            y_end = y_max
        ax.axhspan(
            ymin=y_start,
            ymax=y_end,
            color=color,
            alpha=COLORS['band_alpha'],
            zorder=0
        )

    # --- FIX 3: Spread colors from extremes inward ---
    colors = get_spread_colors(len(selected_vars))

    legend_elements = []

    for i, var in enumerate(selected_vars):
        color = colors[i]

        if var in bar_vars:
            ax.bar(filtered_df['date'], filtered_df[var], label=var, color=color, alpha=0.7, width=0.8)
        else:
            ax.plot(filtered_df['date'], filtered_df[var], label=var, color=color, linewidth=2)

        legend_elements.append(
            plt.Line2D([0], [0], marker='o', color='w', markerfacecolor=color, markersize=10, label=var)
        )

    # Red vertical bars where exertion == 1 (from bottom to top)
    exertion_mask = filtered_df['exertion'] == 1
    if exertion_mask.any():
        exertion_dates = filtered_df.loc[exertion_mask, 'date']
        ax.vlines(
            x=exertion_dates,
            ymin=0,
            ymax=10,
            color=COLORS['exertion_dot'],
            zorder=5,
            linewidths=1.5,
            alpha=0.7
        )
        legend_elements.append(
            plt.Line2D([0], [0], color=COLORS['exertion_dot'], linewidth=2, label='Exertion = 1')
        )

    # Axes formatting
    ax.set_ylim(0, 10)
    ax.set_title("Energy and variables", fontsize=14, fontweight='bold')
    ax.yaxis.set_major_locator(plt.MultipleLocator(1))
    ax.grid(axis='y', alpha=COLORS['grid_alpha'])
    ax.grid(axis='x', visible=False)

    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    plt.setp(ax.get_xticklabels(), rotation=0, ha='center')

    # Legend on the right
    ax.legend(handles=legend_elements, loc='center left', bbox_to_anchor=(1.02, 0.5), fontsize=9, frameon=False)

    fig.tight_layout()
    st.pyplot(fig)
else:
    st.info("Select at least one variable to display.")