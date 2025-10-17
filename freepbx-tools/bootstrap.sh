#!/bin/bash
# bootstrap.sh - The ultimate lazy solution to the chmod chicken-and-egg problem
# This tiny script makes everything executable in one go

chmod +x *.sh bin/*.sh *.py bin/*.py 2>/dev/null
echo "✅ All scripts are now executable!"
echo "📋 Next: sudo ./install.sh"