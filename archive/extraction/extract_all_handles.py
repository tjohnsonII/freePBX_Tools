import csv
import os

CSV_PATH = os.path.join('freepbx-tools', 'bin', '123net_internal_docs', 'vpbx_comprehensive', 'table_data.csv')
OUT_PATH = 'customer_handles.txt'

def extract_handles(csv_path, out_path):
    handles = set()
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            handle = row.get('Handle')
            if handle and handle.strip():
                handles.add(handle.strip())
    with open(out_path, 'w', encoding='utf-8') as f:
        for handle in sorted(handles):
            f.write(handle + '\n')

if __name__ == '__main__':
    extract_handles(CSV_PATH, OUT_PATH)
    print(f'Extracted {OUT_PATH} with {len(open(OUT_PATH).readlines())} handles.')
