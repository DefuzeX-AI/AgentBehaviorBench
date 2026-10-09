#!/bin/bash

# Grid search script for optimizing hyperparameters for TripleMomentumStrategy

start_date="20250101"
end_date="20251231"
# Define parameter ranges
BIAS_NS=(15 20 25)
MOMENTUM_DAYS=(20 25 30)
SLOPE_NS=(15 20 25)
HOLD_PERIODS=(15 20 25)

# Output directory for results
OUTPUT_DIR="output/tm_grid_search_results"
mkdir -p "$OUTPUT_DIR"

# Log file
LOG_FILE="$OUTPUT_DIR/$(date +%Y%m%d_%H%M%S).log"
echo "Starting grid search for TripleMomentumStrategy at $(date)" > "$LOG_FILE"
echo "start_date: $start_date, end_date: $end_date" >> "$LOG_FILE"

# Loop through all combinations
for bias_n in "${BIAS_NS[@]}"; do
    for momentum_day in "${MOMENTUM_DAYS[@]}"; do
        for slope_n in "${SLOPE_NS[@]}"; do
            for hp in "${HOLD_PERIODS[@]}"; do
                echo "Running with bias_n=$bias_n, momentum_day=$momentum_day, slope_n=$slope_n, hold_period=$hp" | tee -a "$LOG_FILE"
                
                OUTPUT_FILE="$OUTPUT_DIR/tm_backtest_b${bias_n}_m${momentum_day}_s${slope_n}_h${hp}.png"
                
                # Capture output to extract metrics if needed, or just run it
                RESULT=$(python main.py \
                    --strategy TripleMomentumStrategy \
                    --start_date $start_date \
                    --end_date $end_date \
                    --bias_n $bias_n \
                    --momentum_day $momentum_day \
                    --slope_n $slope_n \
                    --hold_period $hp 2>&1)
                    
                # Extract Total Return using grep
                    TOTAL_RETURN=$(echo "$RESULT" | grep "Total Return" | cut -d: -f2)
                    
                    if [ -z "$TOTAL_RETURN" ]; then
                        echo "  Failed to extract return. Check logs." | tee -a "$LOG_FILE"
                        echo "Error Output:" >> "$LOG_FILE"
                        echo "$RESULT" >> "$LOG_FILE"
                    else
                        echo "  Total Return: $TOTAL_RETURN" | tee -a "$LOG_FILE"
                    fi

                    # echo "Completed run, output saved to $OUTPUT_FILE" | tee -a "$LOG_FILE"
                    echo "------------------------------------------------" >> "$LOG_FILE"
                done
            done
        done
done

echo "Grid search completed at $(date)" | tee -a "$LOG_FILE"
