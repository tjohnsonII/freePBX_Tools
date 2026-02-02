import os, json, time
from selenium import webdriver
from selenium.webdriver.edge.options import Options

root = os.environ["EDGE_PROFILE_DIR"]

opts = Options()
opts.add_argument("--user-data-dir=" + root)

d = webdriver.Edge(options=opts)
d.get("https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi")
time.sleep(2)

print("TITLE =", d.title)
print("URL   =", d.current_url)

# Selenium view
sc = d.get_cookies()
print("selenium_cookie_count =", len(sc))

# CDP view (stronger)
try:
    d.execute_cdp_cmd("Network.enable", {})
    allc = d.execute_cdp_cmd("Network.getAllCookies", {})
    cookies = allc.get("cookies", [])
    # show only relevant domains
    interesting = [c for c in cookies if "123.net" in c.get("domain","")]
    print("cdp_cookie_count_total =", len(cookies))
    print("cdp_cookie_count_123net =", len(interesting))
    print("cdp_cookie_domains_sample =", sorted({c.get("domain") for c in interesting})[:10])
except Exception as e:
    print("CDP failed:", repr(e))

d.quit()
