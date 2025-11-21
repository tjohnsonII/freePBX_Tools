#!/usr/bin/env python3
#!/usr/bin/env python3
"""
Pre-commit security verification script

This script scans all staged files in a git repository for patterns that may indicate
the presence of sensitive data (such as passwords, API keys, secrets, or IP addresses).
It is intended to be used as a pre-commit hook to prevent accidental commits of secrets.

VARIABLE MAP LEGEND
-------------------
Colors           : ANSI color code class for terminal output
result           : subprocess.CompletedProcess, result of running a shell command
filepath         : str, path to a file being scanned
sensitive_patterns: dict, regex patterns mapped to description strings
issues           : list of dict, each with type, match, and position for a finding
content          : str, file contents being scanned
files            : list of str, files staged for commit
all_issues       : dict, filepath -> list of issues found in that file
exit_code        : int, exit status for the script (0 = safe, 1 = unsafe)
"""

import subprocess
import re
import sys


# ANSI color codes for pretty terminal output
class Colors:
    RED = '\033[91m'      # Red text
    GREEN = '\033[92m'    # Green text
    YELLOW = '\033[93m'   # Yellow text
    BLUE = '\033[94m'     # Blue text
    BOLD = '\033[1m'      # Bold text
    RESET = '\033[0m'     # Reset to default


def check_staged_files():
    """
    Get a list of files currently staged for commit in git.
    Returns:
        list of str: Filenames staged for commit.
    """
    result = subprocess.run(['git', 'diff', '--cached', '--name-only'], 
                            capture_output=True, text=True)
    # Split output into lines, ignore empty
    return result.stdout.strip().split('\n') if result.stdout.strip() else []


def check_for_sensitive_patterns(filepath):
    """
    Check the contents of a file for patterns that may indicate sensitive data.
    Args:
        filepath (str): Path to the file to scan.
    Returns:
        list of dict: Issues found, each with type, match, and position.
    """
    # Define regex patterns for sensitive data
    sensitive_patterns = {
        r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b': 'IP Address',
        r'password\s*=\s*["\"]([^"\"]{8,})["\"]': 'Password Assignment',
        r'api[_-]?key\s*[=:]\s*["\']?[\w-]{20,}': 'API Key',
        r'secret\s*[=:]\s*["\']?[\w-]{20,}': 'Secret Token',
        r'ftp[_-]?pass': 'FTP Password Reference',
        r'ssh[_-]?password': 'SSH Password Reference',
    }
    issues = []
    try:
        # Read file content (ignore encoding errors)
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        # Search for each pattern
        for pattern, issue_type in sensitive_patterns.items():
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                # Extract context around the match to help filter false positives
                line_start = max(0, match.start() - 100)
                context = content[line_start:match.end()+50]
                # Skip common false positives (e.g., code examples, input prompts)
                if 'getpass' in context or 'input(' in context:
                    continue
                if '# Example' in context or '"""' in context:
                    continue
                # Record the issue
                issues.append({
                    'type': issue_type,
                    'match': match.group(0)[:50],
                    'position': match.start()
                })
    except Exception as e:
        # If file can't be read, record the error
        issues.append({
            'type': 'File Read Error',
            'match': str(e),
            'position': 0
        })
    return issues


def main():
    """
    Main entry point for the pre-commit scan.
    Scans all staged files for sensitive data patterns and prints a summary.
    Returns:
        int: 0 if clear, 1 if issues found.
    """
    print(f"{Colors.BOLD}{Colors.BLUE}🔒 Pre-Commit Security Scan{Colors.RESET}\n")
    # Get list of staged files
    staged_files = check_staged_files()
    if not staged_files or staged_files == ['']:
        print(f"{Colors.YELLOW}⚠ No files staged for commit{Colors.RESET}")
        return
    print(f"Scanning {len(staged_files)} staged files...\n")
    all_clear = True
    for filepath in staged_files:
        # Skip binary files and common non-source files
        if filepath.endswith(('.pyc', '.db', '.png', '.jpg', '.gif')):
            continue
        # Scan file for sensitive patterns
        issues = check_for_sensitive_patterns(filepath)
        if issues:
            all_clear = False
            print(f"{Colors.RED}⚠ {filepath}{Colors.RESET}")
            for issue in issues[:3]:  # Show up to 3 issues per file
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


# Run the main function if this script is executed directly
if __name__ == '__main__':
    sys.exit(main())
