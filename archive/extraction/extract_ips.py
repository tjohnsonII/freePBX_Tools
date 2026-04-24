
# FUNCTION MAP LEGEND
# -------------------
# This script is procedural and does not define any functions.
# It reads '123NET Admin.csv', extracts the 'IP' column, and prints each IP address found.

import csv

with open("123NET Admin.csv", newline='') as f:
    reader = csv.DictReader(f)
    for row in reader:
        ip = row.get("IP")
        if ip and ip.lower() != "ip":
            print(ip)