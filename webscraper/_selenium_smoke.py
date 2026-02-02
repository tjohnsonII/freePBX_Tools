import os, time
from selenium import webdriver
from selenium.webdriver.edge.options import Options

root = os.environ["EDGE_PROFILE_DIR"]
opts = Options()
opts.add_argument("--user-data-dir=" + root)
opts.add_argument("--window-size=1400,900")

d = webdriver.Edge(options=opts)
d.get("https://example.com")
print("TITLE =", d.title)
time.sleep(3)
d.quit()
