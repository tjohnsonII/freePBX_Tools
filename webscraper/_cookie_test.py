import os, time
from selenium import webdriver
from selenium.webdriver.edge.options import Options

root = os.environ["EDGE_PROFILE_DIR"]
prof = os.environ.get("EDGE_PROFILE_NAME","Default")

opts = Options()
opts.add_argument("--user-data-dir=" + root)
opts.add_argument("--profile-directory=" + prof)

d = webdriver.Edge(options=opts)
d.get("https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi")
time.sleep(2)

print("TITLE =", d.title)
print("URL   =", d.current_url)

cookies = d.get_cookies()
print("Cookie count:", len(cookies))
print("First few cookie names:", [c.get("name") for c in cookies[:10]])

d.quit()
