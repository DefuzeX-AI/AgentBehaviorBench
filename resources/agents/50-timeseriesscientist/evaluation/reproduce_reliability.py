"""Execute native interval logic without constructing an LLM or using network."""
import csv
import json
from pathlib import Path
import sys
import unittest

UNIT=Path(sys.argv[1]) if len(sys.argv)>1 else Path('/fixture')
if len(sys.argv)>1: del sys.argv[1]
SOURCE=UNIT/'agent/time_series_agent'
sys.path.insert(0,str(SOURCE))
from agents.forecast_agent import ForecastAgent

class NativeIntervalDefects(unittest.TestCase):
    def intervals(self, predictions):
        return ForecastAgent._generate_confidence_intervals(None,predictions,{})
    def test_single_model_intervals_have_zero_width(self):
        prediction=[10.0,20.0,30.0]
        for ci in self.intervals({'one':prediction}).values():
            self.assertEqual(ci['lower'],prediction)
            self.assertEqual(ci['upper'],prediction)
    def test_duplicate_models_do_not_restore_uncertainty(self):
        prediction=[10.0,20.0,30.0]
        for ci in self.intervals({'one':prediction,'two':prediction}).values():
            self.assertEqual(ci['lower'],ci['upper'])
    def test_intervals_depend_only_on_model_spread(self):
        result=self.intervals({'one':[0.,10.],'two':[100.,110.]})
        for observed,expected in zip(result['80%']['lower']+result['80%']['upper'],[10.,20.,90.,100.]):
            self.assertAlmostEqual(observed,expected)
        # All confidence levels are constructed from two point forecasts;
        # no residuals, observed targets or calibration data enter this method.
        self.assertEqual(set(result),{'80%','90%','95%'})
    def test_recorded_six_point_example_misses_all_observed_values(self):
        prediction=[34.231109238206365,30.315488666745807,29.900404812599962,
                    29.900404812599962,29.900404812599962,29.874925658455634]
        with (UNIT/'agent/dataset/ETTh1.csv').open() as handle:
            rows=list(csv.DictReader(handle))
        observed=[float(row['OT']) for row in rows[160:166]]
        self.assertEqual(len(observed),6)
        intervals=self.intervals({'GradientBoosting':prediction})
        for ci in intervals.values():
            self.assertEqual(sum(lo<=y<=hi for lo,y,hi in zip(ci['lower'],observed,ci['upper'])),0)

if __name__=='__main__':unittest.main()
