import csv

with open("123NET Admin.csv", newline='') as f:
    reader = csv.DictReader(f)
    for row in reader:
        ip = row.get("IP")
        if ip and ip.lower() != "ip":
            print(ip)