#!/usr/bin/env python3
"""
Pre-commit security verification script
Scans staged files for potential sensitive data patterns
"""

import subprocess
import re
import sys

class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    RESET = '\033[0m'

def check_staged_files():
    """Get list of staged files"""
    result = subprocess.run(['git', 'diff', '--cached', '--name-only'], 
                          capture_output=True, text=True)
    return result.stdout.strip().split('\n') if result.stdout.strip() else []

def check_for_sensitive_patterns(filepath):
    """Check file content for sensitive patterns"""
    sensitive_patterns = {
        r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b': 'IP Address',
        r'password\s*=\s*["\']([^"\']{8,})["\']': 'Password Assignment',
        r'api[_-]?key\s*[=:]\s*["\']?[\w-]{20,}': 'API Key',
        r'secret\s*[=:]\s*["\']?[\w-]{20,}': 'Secret Token',
        r'ftp[_-]?pass': 'FTP Password Reference',
        r'ssh[_-]?password': 'SSH Password Reference',
    }
    
    issues = []
    
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            
        for pattern, issue_type in sensitive_patterns.items():
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                # Skip false positives (comments, documentation)
                line_start = max(0, match.start() - 100)
                context = content[line_start:match.end()+50]
                
                # Allow password validation/checking code
                if 'getpass' in context or 'input(' in context:
                    continue
                if '# Example' in context or '"""' in context:
                    continue
                    
                issues.append({
                    'type': issue_type,
                    'match': match.group(0)[:50],
                    'position': match.start()
                })
    except Exception as e:
        issues.append({
            'type': 'File Read Error',
            'match': str(e),
            'position': 0
        })
    
    return issues

def main():
    print(f"{Colors.BOLD}{Colors.BLUE}🔒 Pre-Commit Security Scan{Colors.RESET}\n")
    
    # Get staged files
    staged_files = check_staged_files()
    
    if not staged_files or staged_files == ['']:
        print(f"{Colors.YELLOW}⚠ No files staged for commit{Colors.RESET}")
        return
    
    print(f"Scanning {len(staged_files)} staged files...\n")
    
    all_clear = True
    
    for filepath in staged_files:
        # Skip binary files and specific safe patterns
        if filepath.endswith(('.pyc', '.db', '.png', '.jpg', '.gif')):
            continue
        
        issues = check_for_sensitive_patterns(filepath)
        
        if issues:
            all_clear = False
            print(f"{Colors.RED}⚠ {filepath}{Colors.RESET}")
            for issue in issues[:3]:  # Show max 3 issues per file
                print(f"  - {issue['type']}: {issue['match']}")
            if len(issues) > 3:
                print(f"  ... and {len(issues) - 3} more issues")
            print()
    
    print("-" * 70)
    
    if all_clear:
        print(f"{Colors.GREEN}{Colors.BOLD}✅ CLEAR - No sensitive data detected{Colors.RESET}")
        print(f"\n{Colors.BLUE}Safe to commit:{Colors.RESET}")
        for f in staged_files:
            print(f"  ✓ {f}")
        return 0
    else:
        print(f"{Colors.RED}{Colors.BOLD}⛔ WARNING - Potential sensitive data found{Colors.RESET}")
        print(f"\n{Colors.YELLOW}Review the files above before committing{Colors.RESET}")
        return 1

if __name__ == '__main__':
    sys.exit(main())
