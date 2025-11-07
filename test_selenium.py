#!/usr/bin/env python3
"""Test Selenium setup"""

try:
    print("Importing selenium...")
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    print("✓ Selenium imported")
    
    print("\nAttempting to start Chrome...")
    options = webdriver.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    
    driver = webdriver.Chrome(options=options)
    print("✓ Chrome started successfully!")
    
    print("\nNavigating to test page...")
    driver.get("https://www.google.com")
    print(f"✓ Page title: {driver.title}")
    
    print("\nClosing browser...")
    driver.quit()
    print("✓ Test successful!")
    
except Exception as e:
    print(f"\n✗ Error: {e}")
    print(f"\nError type: {type(e).__name__}")
    
    if "chromedriver" in str(e).lower() or "driver" in str(e).lower():
        print("\n" + "="*80)
        print("ChromeDriver may not be installed or not in PATH.")
        print("Install with: pip install webdriver-manager")
        print("="*80)
