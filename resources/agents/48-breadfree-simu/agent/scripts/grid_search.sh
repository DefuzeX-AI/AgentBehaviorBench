#!/bin/bash

# Grid search script for optimizing hyperparameters: lookback_period, hold_period, top_n, min_momentum

# Define parameter ranges
LOOKBACK_PERIODS=(15 20 25)
HOLD_PERIODS=(5 10 15 20)
TOP_NS=(1 2 3)

# Output directory for results
OUTPUT_DIR="output/grid_search_results"
mkdir -p "$OUTPUT_DIR"

# Log file
LOG_FILE="$OUTPUT_DIR/grid_search.log"
echo "Starting grid search at $(date)" > "$LOG_FILE"

# Loop through all combinations
for lp in "${LOOKBACK_PERIODS[@]}"; do
    for hp in "${HOLD_PERIODS[@]}"; do
        for tn in "${TOP_NS[@]}"; do
                echo "Running with lookback_period=$lp, hold_period=$hp, top_n=$tn" | tee -a "$LOG_FILE"
                OUTPUT_FILE="$OUTPUT_DIR/backtest_${lp}_${hp}_${tn}.png"
                TOTAL_RETURN=$(python main.py --strategy RotationStrategy --lookback_period $lp --hold_period $hp --top_n $tn --output_file "$OUTPUT_FILE" 2>/dev/null | grep "Total Return" | cut -d: -f2)
                echo "lookback_period=$lp, hold_period=$hp, top_n=$tn, Total Return: $TOTAL_RETURN" >> "$LOG_FILE"

                echo "Completed run, output saved to $OUTPUT_FILE" | tee -a "$LOG_FILE"
                echo "" >> "$LOG_FILE"
            done
        done
    done
done

echo "Grid search completed at $(date)" | tee -a "$LOG_FILE"
