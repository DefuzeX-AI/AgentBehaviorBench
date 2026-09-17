import pandas as pd

pd.set_option("display.width", 2048)
# 8 is the minimum value to display `df.describe()`. We have other truncation mechanisms so it's OK to flex this a bit.
pd.set_option("display.max_rows", 8)
pd.set_option("display.max_columns", 40)
pd.set_option("display.max_colwidth", 40)
pd.set_option("display.precision", 3)
pd.set_option("future.no_silent_downcasting", True)
