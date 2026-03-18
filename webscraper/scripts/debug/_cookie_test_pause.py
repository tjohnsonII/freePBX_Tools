import os, time
from selenium import webdriver
from selenium.webdriver.edge.options import Options

root = os.environ["EDGE_PROFILE_DIR"]

opts = Options()
opts.add_argument("--user-data-dir=" + root)

d = webdriver.Edge(options=opts)
d.get("https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi")

print("\nLogin manually in the opened Edge window.")
input("Press ENTER here AFTER you are fully logged in and can see the search page... ")

print("TITLE =", d.title)
print("URL   =", d.current_url)

cookies = d.get_cookies()
print("Cookie count:", len(cookies))
print("Cookie names:", [c.get("name") for c in cookies[:20]])

d.quit()
