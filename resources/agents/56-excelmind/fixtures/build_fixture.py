"""Build the public synthetic workbook; no user/business data or model calls."""
import csv
from pathlib import Path
from openpyxl import Workbook

def build(target):
    target = Path(target)
    if target.exists():
        raise FileExistsError('Refusing to overwrite workbook')
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Sales'
    with (Path(__file__).parent / 'sales.csv').open() as stream:
        rows = list(csv.reader(stream))
    sheet.append(rows[0])
    for row in rows[1:]:
        sheet.append(row[:3] + [int(value) for value in row[3:]])
    target.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(target)
    workbook.close()

if __name__ == '__main__':
    import sys
    build(sys.argv[1])
