#!/usr/bin/env python3

"""
Test Selenium Setup Script
-------------------------
This script verifies that Selenium and ChromeDriver are installed and working.
It attempts to launch a Chrome browser, navigate to Google, and print the page title.
Intended for troubleshooting Selenium environment issues.

VARIABLE MAP LEGEND
-------------------

options : webdriver.ChromeOptions
    Chrome browser options for Selenium
driver  : webdriver.Chrome
    Selenium WebDriver instance for Chrome
e       : Exception
    Exception object for error handling
"""

try:
    # Step 1: Import Selenium and required modules
    print("Importing selenium...")
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    print("✓ Selenium imported")

    # Step 2: Set Chrome options (disable automation detection)
    print("\nAttempting to start Chrome...")
    options = webdriver.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")

    # Step 3: Start Chrome browser with options
    driver = webdriver.Chrome(options=options)
    print("✓ Chrome started successfully!")

    # Step 4: Navigate to a test page (Google)
    print("\nNavigating to test page...")
    driver.get("https://www.google.com")
    print(f"✓ Page title: {driver.title}")

    # Step 5: Close the browser
    print("\nClosing browser...")
    driver.quit()
    print("✓ Test successful!")

except Exception as e:
    # Handle and print any errors that occur during the test
    print(f"\n✗ Error: {e}")
    print(f"\nError type: {type(e).__name__}")

    # Special message if ChromeDriver is missing or not in PATH
    if "chromedriver" in str(e).lower() or "driver" in str(e).lower():
        print("\n" + "="*80)
        print("ChromeDriver may not be installed or not in PATH.")
        print("Install with: pip install webdriver-manager")
        print("="*80)
