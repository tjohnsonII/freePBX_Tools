#!/usr/bin/env python
"""
Test script to verify BeautifulSoup4 and requests are properly installed
"""

def test_imports():
    print("🧪 Testing Python package imports...")
    
    try:
        import sys
        print(f"✅ Python version: {sys.version}")
        print(f"✅ Python executable: {sys.executable}")
    except Exception as e:
        print(f"❌ Python import failed: {e}")
        return False
    
    try:
        import requests
        print(f"✅ requests version: {requests.__version__}")
    except ImportError as e:
        print(f"❌ requests import failed: {e}")
        return False
    
    try:
        import bs4
        from bs4 import BeautifulSoup
        print(f"✅ BeautifulSoup4 version: {bs4.__version__}")
    except ImportError as e:
        print(f"❌ BeautifulSoup4 import failed: {e}")
        return False
    
    # Test basic functionality
    try:
        html = "<html><body><h1>Test</h1></body></html>"
        soup = BeautifulSoup(html, 'html.parser')
        h1_tag = soup.find('h1')
        title = h1_tag.text if h1_tag else "No h1 found"
        print(f"✅ BeautifulSoup4 parsing test: '{title}'")
    except Exception as e:
        print(f"❌ BeautifulSoup4 functionality test failed: {e}")
        return False
    
    print("\n🎉 All imports and tests passed!")
    return True

if __name__ == "__main__":
    test_imports()