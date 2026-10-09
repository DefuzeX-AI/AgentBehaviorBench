#!/usr/bin/env python3

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import re
import os
import glob

# 1. Find latest log file
log_dir = "output/tm_grid_search_results"
if not os.path.exists(log_dir):
    print(f"Log directory {log_dir} not found.")
    exit(1)

list_of_files = glob.glob(os.path.join(log_dir, '*.log'))
if not list_of_files:
    print(f"No log files found in {log_dir}")
    exit(1)
latest_log_file = max(list_of_files, key=os.path.getctime)
print(f"Processing log file: {latest_log_file}")

# 2. Parse data
data = []
current_params = {}

with open(latest_log_file, 'r') as f:
    for line in f:
        line = line.strip()
        if line.startswith("Running with"):
            # Format: Running with bias_n=15, momentum_day=20, slope_n=15, hold_period=15, top_n=1
            parts = line.replace("Running with ", "").split(", ")
            current_params = {}
            for part in parts:
                if "=" in part:
                    p_name, p_val = part.split("=")
                    current_params[p_name] = int(p_val)
        
        elif line.startswith("Total Return:"):
             # Format: Total Return:  39.87%
             try:
                 val_str = line.split(":")[1].strip().replace("%", "")
                 if val_str and current_params:
                     current_params['total_return'] = float(val_str)
                     data.append(current_params.copy())
                     current_params = {} 
             except Exception as e:
                 print(f"Error parsing return line: {line} - {e}")

if not data:
    print("No data parsed.")
    exit(1)

df = pd.DataFrame(data)

# Handle top_n if missing
if 'top_n' not in df.columns:
    df['top_n'] = 1

# Save to CSV
csv_path = latest_log_file.replace(".log", ".csv")
df.to_csv(csv_path, index=False)
print(f"Data saved to {csv_path}")

# Print Top 10
print("\nTop 10 Configurations:")
print(df.sort_values(by="total_return", ascending=False).head(10).to_string(index=False))

# 3. Plotting
# We have dimensions: bias_n, momentum_day, slope_n, hold_period, top_n
# We will create separate plots for each top_n
unique_top_ns = sorted(df['top_n'].unique())

for tn in unique_top_ns:
    df_tn = df[df['top_n'] == tn]
    
    # We want to plot bias_n vs momentum_day.
    # We need to handle slope_n and hold_period.
    # Let's create a grid of subplots for slope_n (cols) and hold_period (rows)
    
    unique_slopes = sorted(df_tn['slope_n'].unique())
    unique_holds = sorted(df_tn['hold_period'].unique())
    
    nrows = len(unique_holds)
    ncols = len(unique_slopes)
    
    # Adjust figure size
    # figsize=(width, height)
    fig, axes = plt.subplots(nrows, ncols, figsize=(max(ncols * 4, 10), max(nrows * 3, 6)), squeeze=False)
    fig.suptitle(f"Total Return Heatmap (Top N = {tn})\nX: Momentum Day, Y: Bias N", fontsize=16)
    
    # Calculate vmin and vmax for consistent color scale across all subplots
    vmin = df_tn['total_return'].min()
    vmax = df_tn['total_return'].max()

    for r, hp in enumerate(unique_holds):
        for c, sn in enumerate(unique_slopes):
            ax = axes[r, c]
            subset = df_tn[(df_tn['hold_period'] == hp) & (df_tn['slope_n'] == sn)]
            
            if subset.empty:
                ax.text(0.5, 0.5, "No Data", ha='center', va='center')
                continue
            
            # Use pivot to create matrix for heatmap
            # bias_n on Y, momentum_day on X
            pivot = None
            try:
                pivot = subset.pivot(index='bias_n', columns='momentum_day', values='total_return')
            except ValueError as e:
                # Handle duplicate entries if any (shouldn't happen with proper grid search)
                print(f"Warning: Duplicate entries found for hp={hp}, sn={sn}, tn={tn}. taking mean.")
                pivot = subset.groupby(['bias_n', 'momentum_day'])['total_return'].mean().unstack()
            
            if pivot is not None:
                sns.heatmap(pivot, annot=True, fmt=".1f", cmap="RdYlGn", ax=ax, 
                            cbar=(c == ncols-1), vmin=vmin, vmax=vmax)

            
            title = []
            if r == 0: title.append(f"Slope N = {sn}")
            if c == 0: ax.set_ylabel(f"Hold Period = {hp}\nBias N")
            else: ax.set_ylabel("")
            
            if title: ax.set_title("\n".join(title))
            ax.set_xlabel("Momentum Day" if r == nrows-1 else "")

    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    plot_filename = latest_log_file.replace(".log", f"_heatmap_top{tn}.png")
    plt.savefig(plot_filename)
    print(f"Heatmap saved to {plot_filename}")

print("Done.")