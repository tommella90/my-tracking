import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import date, timedelta
import streamlit as st

st.set_page_config(page_title="Energy Tracker", layout="wide")

# --- Color Configuration (Modify all colors here) ---
# Chart colors
COLORS = {
    'spine': '#333333',
    'grid_alpha': 0.3,
    'exertion_dot': "#D61919",
    'exertion_dot_edge': 'black',
    'band_alpha': 0.1,
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

# Custom color palette for variable lines
# Add/remove colors as needed
VARIABLE_COLORS = [
    '#D61919',  # red
    '#1982D6',  # blue
    '#19D635',  # green
    '#D6D119',  # yellow
    '#8F19D6',  # purple
    '#D66A19',  # orange
    '#19D6A8',  # teal
    '#D6198F',  # pink
    '#5A19D6',  # indigo
    '#19D682',  # sea green
]

def get_spread_colors(n):
    """Pick n colors from custom palette, spreading from extremes inward."""
    if n == 0:
        return []
    if n == 1:
        return [VARIABLE_COLORS[0]]
    if n == 2:
        return [VARIABLE_COLORS[0], VARIABLE_COLORS[-1]]
    # For n>=3: start with extremes, then fill from the middle outward
    # Generate candidate positions: 0, last_index, mid, quarter, three-quarter, etc.
    num_colors = len(VARIABLE_COLORS)
    positions = []
    for level in range(20):  # enough levels for reasonable n
        if level == 0:
            positions.extend([0, num_colors - 1])
        elif level == 1:
            positions.append((num_colors - 1) // 2)
        else:
            # subdivide existing intervals, pick midpoints
            new_positions = []
            sorted_pos = sorted(positions)
            for i in range(len(sorted_pos) - 1):
                midpoint = (sorted_pos[i] + sorted_pos[i + 1]) / 2
                new_positions.append(int(round(midpoint)))
            positions.extend(new_positions)
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for p in positions:
        if p < 0 or p >= num_colors:
            continue
        if p not in seen:
            seen.add(p)
            unique.append(p)
        if len(unique) >= n:
            break
    return [VARIABLE_COLORS[p] for p in unique[:n]]

# --- Data Loading ---
@st.cache_data
def load_data():
    df = pd.read_excel('data/otherData/energy_tracker.ods', engine='odf')
    columns = ['date', 'stress_level(1-5)', 'sleep_hours', 'physical activity', 'focus', 'cognitive-usage', 'hyperactive-brain', 'total activity', 'social activity', 'POTS 0-5', 'mood', 'energy', 'exertion', 'fatigue', 'activity', 'sympthoms', 'poop1', 'supplements', 'notes1', 'notes 2', ]
    df = df[columns]
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df = df.dropna(subset=['date']).sort_values('date').reset_index(drop=True)
    return df

df = load_data()
# df['total activity'] = df['total activity'].astype(float)

# replace 's' with ''
df['total activity'] = df['total activity'].astype(str).str.replace('s', '', regex=False)
df['total activity'] = pd.to_numeric(df['total activity'], errors='coerce')

# replace nan with 0
df['physical activity'] = df['physical activity'].fillna(0)
df['physical activity'] = pd.to_numeric(df['physical activity'], errors='coerce')

st.write(df.dtypes)
# --- CSV Download ---
st.download_button(
    label="⬇️ Download CSV",
    data=df.to_csv(index=False).encode('utf-8'),
    file_name="energy_tracker.csv",
    mime="text/csv"
)

# --- Table (last day + 5 days before) ---
st.subheader("Last 6 days")
today = pd.to_datetime("today").normalize()
# Get today and 5 days before (6 days total)
today_date = pd.to_datetime(today)
start_date = today_date - timedelta(days=5)
last_6_days = df[(df['date'] >= start_date) & (df['date'] <= today_date)]
st.dataframe(last_6_days, use_container_width=True)

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
chart_vars = ['stress_level(1-5)', 'sleep_hours', 'physical activity', 'focus', 'cognitive-usage', 'total activity', 'social activity', 'POTS 0-5', 'mood', 'energy', 'fatigue']

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

    # Dots on energy line where exertion == 1
    exertion_mask = filtered_df['exertion'] == 1
    if exertion_mask.any() and 'energy' in filtered_df.columns:
        energy_vals = filtered_df.loc[exertion_mask, 'energy']
        ax.scatter(
            filtered_df.loc[exertion_mask, 'date'],
            energy_vals,
            color=COLORS['exertion_dot'],
            zorder=5,
            s=60,
            marker='o',
            edgecolors=COLORS['exertion_dot_edge'],
            linewidths=0.5
        )
        legend_elements.append(
            plt.Line2D([0], [0], marker='o', color='w', markerfacecolor=COLORS['exertion_dot'], markersize=10, markeredgecolor=COLORS['exertion_dot_edge'], label='Exertion = 1')
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