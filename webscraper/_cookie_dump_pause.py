import os, time, json
from selenium import webdriver
from selenium.webdriver.edge.options import Options

root = os.environ["EDGE_PROFILE_DIR"]

opts = Options()
opts.add_argument("--user-data-dir=" + root)

d = webdriver.Edge(options=opts)
d.get("https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi")

print("\nLOGIN NOW in the opened Edge window.")
print("When you can see the search box and results normally, come back here.")
input("Press ENTER to dump cookies... ")

# Selenium view
sc = d.get_cookies()
print("selenium_cookie_count =", len(sc))

# CDP view
d.execute_cdp_cmd("Network.enable", {})
allc = d.execute_cdp_cmd("Network.getAllCookies", {})
cookies = allc.get("cookies", [])
interesting = [c for c in cookies if "123.net" in (c.get("domain","") or "")]
print("cdp_cookie_count_total =", len(cookies))
print("cdp_cookie_count_123net =", len(interesting))
print("cdp_cookie_domains_sample =", sorted({c.get("domain") for c in interesting})[:10])

# Write to file so we can inspect
out = {
  "selenium": sc,
  "cdp_total": cookies,
  "cdp_123net": interesting
}
open(r"webscraper\output\cookie_dump.json","w",encoding="utf-8").write(json.dumps(out, indent=2))
d.save_screenshot(r"webscraper\output\after_login.png")
open(r"webscraper\output\after_login.html","w",encoding="utf-8").write(d.page_source)

print("\nSaved webscraper/output/cookie_dump.json, after_login.png, after_login.html")
input("Press ENTER to close browser... ")
d.quit()
