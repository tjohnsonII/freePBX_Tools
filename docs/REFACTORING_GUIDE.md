# Complete Refactoring Guide: Moving Scripts to bin/

## Overview
If you want to move all Python scripts to `bin/` directory, here are ALL the changes required:

---

## PART 1: File Moves

### Move to bin/
```
analyze_vpbx_phone_configs.py
create_vpbx_database.py
deep_analyze_scraped_data.py
deploy_freepbx_tools.py
deploy_uninstall_tools.py
extract_credentials.py
extract_ips.py
extract_site_companies.py
extract_yealink_companies.py
find_yealink_sites.py
freepbx_tools_manager.py
match_yealink_companies.py
phone_config_analyzer.py
phone_config_analyzer_demo.py
query_vpbx.py
query_w60.py
run_comprehensive_scrape.py
scrape_123net_docs.py
scrape_123net_docs_selenium.py
scrape_vpbx_tables.py
scrape_vpbx_tables_comprehensive.py
test_comprehensive_scrape.py
test_dashboard.py
test_phone_analyzer_integration.py
test_selenium.py
ultimate_vpbx_analyzer.py
verify_commit_safety.py
view_dashboard.py
vpbx_query_interactive.py
web_manager.py
```

### Stay at Root
```
config.py (MUST stay - imported by scripts)
config.example.py
ProductionServers.txt (MUST stay - hard-coded in scripts)
vpbx_data.db (MUST stay - hard-coded in scripts)
*.sql files (referenced by scripts)
README.md
.gitignore
run_all.sh, summarize.sh, push_env_check.sh, remote_uninstall.ps1
```

---

## PART 2: Code Changes Required

### File: `bin/freepbx_tools_manager.py`

**Line 80: config.py path**
```python
# BEFORE:
with open("config.py", "w") as f:

# AFTER:
with open("../config.py", "w") as f:
```

**Line 100: ProductionServers.txt check**
```python
# BEFORE:
if os.path.exists("ProductionServers.txt"):
    return "ProductionServers.txt"

# AFTER:
if os.path.exists("../ProductionServers.txt"):
    return "../ProductionServers.txt"
```

**Line 148: Deploy script call**
```python
# BEFORE:
cmd = ["python", "deploy_freepbx_tools.py", "--servers", servers]

# AFTER:
cmd = ["python", "bin/deploy_freepbx_tools.py", "--servers", servers]
```

**Line 259: Deploy script call**
```python
# BEFORE:
cmd = ["python", "deploy_freepbx_tools.py", "--servers", servers]

# AFTER:
cmd = ["python", "bin/deploy_freepbx_tools.py", "--servers", servers]
```

**Line 292: Test deployment**
```python
# BEFORE:
cmd = ["python", "deploy_freepbx_tools.py", "--servers", "69.39.69.102"]

# AFTER:
cmd = ["python", "bin/deploy_freepbx_tools.py", "--servers", "69.39.69.102"]
```

**Line 324: Config check**
```python
# BEFORE:
if os.path.exists("config.py"):

# AFTER:
if os.path.exists("../config.py"):
```

**Line 443: Phone analyzer call**
```python
# BEFORE:
cmd = ["python", "phone_config_analyzer.py", file_path]

# AFTER:
cmd = ["python", "bin/phone_config_analyzer.py", file_path]
```

**Line 469: Phone analyzer directory call**
```python
# BEFORE:
cmd = ["python", "phone_config_analyzer.py", "--directory", dir_path]

# AFTER:
cmd = ["python", "bin/phone_config_analyzer.py", "--directory", dir_path]
```

**Line 495: Demo file check**
```python
# BEFORE:
demo_file = "phone_config_analyzer_demo.py"
if os.path.exists(demo_file):

# AFTER:
demo_file = "bin/phone_config_analyzer_demo.py"
if os.path.exists(demo_file):
```

---

### File: `bin/phone_config_analyzer_demo.py`

**Line 9: Import statement**
```python
# BEFORE:
from phone_config_analyzer import PhoneConfigAnalyzer, Colors

# AFTER:
# Option 1: Add bin to path
import sys
sys.path.insert(0, os.path.dirname(__file__))
from phone_config_analyzer import PhoneConfigAnalyzer, Colors

# Option 2: Relative import (if making it a package)
from .phone_config_analyzer import PhoneConfigAnalyzer, Colors
```

---

### File: `bin/deploy_freepbx_tools.py`

**Line 22: Import config**
```python
# BEFORE:
from config import FREEPBX_USER, FREEPBX_PASSWORD, FREEPBX_ROOT_PASSWORD

# AFTER:
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import FREEPBX_USER, FREEPBX_PASSWORD, FREEPBX_ROOT_PASSWORD
```

---

### File: `bin/deploy_uninstall_tools.py`

**Line 10: Import config**
```python
# BEFORE:
from config import FREEPBX_USER, FREEPBX_PASSWORD, FREEPBX_ROOT_PASSWORD

# AFTER:
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import FREEPBX_USER, FREEPBX_PASSWORD, FREEPBX_ROOT_PASSWORD
```

---

### File: `bin/view_dashboard.py`

**Line 7: Import config**
```python
# BEFORE:
from config import FREEPBX_USER, FREEPBX_PASSWORD

# AFTER:
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import FREEPBX_USER, FREEPBX_PASSWORD
```

---

### File: `bin/test_dashboard.py`

**Line 6: Import config**
```python
# BEFORE:
from config import FREEPBX_USER, FREEPBX_PASSWORD

# AFTER:
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import FREEPBX_USER, FREEPBX_PASSWORD
```

---

### File: `bin/web_manager.py`

**Line 32-33: ProductionServers.txt**
```python
# BEFORE:
if os.path.exists('ProductionServers.txt'):
    with open('ProductionServers.txt', 'r') as f:

# AFTER:
if os.path.exists('../ProductionServers.txt'):
    with open('../ProductionServers.txt', 'r') as f:
```

**Line 105: Deploy script call**
```python
# BEFORE:
['python', script, '--servers', servers]

# AFTER:
['python', f'bin/{script}', '--servers', servers]
```

**Line 220: Database connection**
```python
# BEFORE:
conn = sqlite3.connect('vpbx_data.db')

# AFTER:
conn = sqlite3.connect('../vpbx_data.db')
```

---

### File: `bin/query_vpbx.py`

**Line 7: Database connection**
```python
# BEFORE:
conn = sqlite3.connect('vpbx_data.db')

# AFTER:
conn = sqlite3.connect('../vpbx_data.db')
```

---

### File: `bin/query_w60.py`

**Line 5: Database connection**
```python
# BEFORE:
conn = sqlite3.connect('vpbx_data.db')

# AFTER:
conn = sqlite3.connect('../vpbx_data.db')
```

---

### File: `bin/vpbx_query_interactive.py`

**Line 74: Database connection**
```python
# BEFORE:
conn = sqlite3.connect('vpbx_data.db')

# AFTER:
conn = sqlite3.connect('../vpbx_data.db')
```

---

### File: `bin/create_vpbx_database.py`

**Lines 11, 306, 526: Database paths**
```python
# BEFORE:
def create_database(db_path='vpbx_data.db'):
def create_sample_queries(db_path='vpbx_data.db'):
print("  sqlite3 vpbx_data.db")

# AFTER:
def create_database(db_path='../vpbx_data.db'):
def create_sample_queries(db_path='../vpbx_data.db'):
print("  sqlite3 ../vpbx_data.db")
```

---

### File: `bin/test_phone_analyzer_integration.py`

**Lines 15-16: File existence check**
```python
# BEFORE:
if os.path.exists("phone_config_analyzer.py"):
    print("✅ phone_config_analyzer.py found")

# AFTER:
if os.path.exists("bin/phone_config_analyzer.py"):
    print("✅ phone_config_analyzer.py found")
```

---

## PART 3: Additional Files to Update

### ROOT: `run_all.sh`
If it calls any Python scripts, update paths:
```bash
# BEFORE:
python deploy_freepbx_tools.py

# AFTER:
python bin/deploy_freepbx_tools.py
```

### ROOT: `README.md`
Update usage examples:
```markdown
# BEFORE:
python deploy_freepbx_tools.py --servers ProductionServers.txt
python phone_config_analyzer.py config.xml

# AFTER:
python bin/deploy_freepbx_tools.py --servers ProductionServers.txt
python bin/phone_config_analyzer.py config.xml
```

---

## PART 4: Flask Web App Template Updates

### File: `templates/index.html` (if exists)
Any JavaScript that calls Python scripts would need path updates.

---

## SUMMARY OF CHANGES

### Files to Modify: **15 Python files**
1. `bin/freepbx_tools_manager.py` - 10 path changes
2. `bin/phone_config_analyzer_demo.py` - 1 import change
3. `bin/deploy_freepbx_tools.py` - 1 import change
4. `bin/deploy_uninstall_tools.py` - 1 import change
5. `bin/view_dashboard.py` - 1 import change
6. `bin/test_dashboard.py` - 1 import change
7. `bin/web_manager.py` - 3 path changes
8. `bin/query_vpbx.py` - 1 path change
9. `bin/query_w60.py` - 1 path change
10. `bin/vpbx_query_interactive.py` - 1 path change
11. `bin/create_vpbx_database.py` - 3 path changes
12. `bin/test_phone_analyzer_integration.py` - 1 path change
13. ROOT: `run_all.sh` - unknown path changes
14. ROOT: `summarize.sh` - unknown path changes
15. ROOT: `README.md` - documentation updates

### Total Changes: **~30+ code changes across 15+ files**

---

## TESTING REQUIRED AFTER CHANGES

1. Test deploy_freepbx_tools.py can find config.py
2. Test freepbx_tools_manager.py menu system
3. Test phone analyzer can import from same directory
4. Test database scripts can find vpbx_data.db
5. Test web app can find ProductionServers.txt
6. Test all subprocess calls work with new paths
7. Test config.py is created in correct location
8. Run all test_*.py scripts

---

## RECOMMENDATION

**Don't do it.** The effort vs. benefit is not worth it:

- 30+ code changes required
- High risk of breaking something
- Need extensive testing
- May introduce bugs
- Violates "if it ain't broke, don't fix it"

**Better approach:**
- Keep scripts at root (it's actually standard for CLI tools)
- Only organize docs and data (which we already did)
- Focus on functionality, not aesthetics
