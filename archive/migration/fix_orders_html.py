"""Fix missing title attributes on SELECT elements in orders_debug.html."""
import re

path = r"e:\DevTools\client-freepbx\freePBX_Tools\webscraper\var\orders\orders_debug.html"

with open(path, encoding="utf-8", errors="ignore") as f:
    content = f.read()

# Map NAME values to descriptive titles
title_map = {
    "updatetype":       "Update Action",
    "time_update":      "Update Time",
    "updatecalendar":   "Update Calendar",
    "web_tech_update":  "Tech List",
}

def add_title(match):
    tag = match.group(0)
    if "title=" in tag.lower():
        return tag
    name_match = re.search(r'NAME="?([^" >]+)"?', tag, re.IGNORECASE)
    if not name_match:
        return tag
    name = name_match.group(1)
    title = title_map.get(name, name.replace("_", " ").title())
    # Insert title= before the closing >
    return tag[:-1] + f' title="{title}">'

before = len(re.findall(r'<SELECT(?![^>]*title=)[^>]*NAME=', content, re.IGNORECASE))
content = re.sub(r'<SELECT[^>]+>', add_title, content, flags=re.IGNORECASE)
after = len(re.findall(r'<SELECT(?![^>]*title=)[^>]*NAME=', content, re.IGNORECASE))

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print(f"Fixed {before - after} SELECT elements. {after} still missing title (should be 0).")
