import os, time, json
from selenium import webdriver
from selenium.webdriver.edge.options import Options

root = os.environ["EDGE_PROFILE_DIR"]

opts = Options()
opts.add_argument("--user-data-dir=" + root)

d = webdriver.Edge(options=opts)
d.get("https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi")
time.sleep(2)

ls = d.execute_script("let o={}; for (let i=0;i<localStorage.length;i++){let k=localStorage.key(i); o[k]=localStorage.getItem(k);} return o;")
ss = d.execute_script("let o={}; for (let i=0;i<sessionStorage.length;i++){let k=sessionStorage.key(i); o[k]=sessionStorage.getItem(k);} return o;")

print("localStorage keys:", list(ls.keys())[:50])
print("sessionStorage keys:", list(ss.keys())[:50])

d.quit()
