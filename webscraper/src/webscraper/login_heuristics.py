from typing import Optional

def ensure_authenticated(driver, url: str) -> bool:
    """Detect common login/SSO pages and return True if authenticated, False otherwise.
    In headless mode, we avoid automating complex SSO/MFA; instead we rely on cookies.
    This function can be extended to fill simple forms when feasible.
    """
    from selenium.webdriver.common.by import By
    try:
        cur = driver.current_url or ""
    except Exception:
        cur = url

    # Heuristic: look for login forms
    try:
        forms = driver.find_elements(By.CSS_SELECTOR, "form")
        inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='password'], input[name*='user'], input[name*='pass']")
        if len(forms) > 0 and len(inputs) > 0:
            # Likely a login page
            print("[AUTH] Login page detected; supply cookies.json for headless auth.")
            return False
    except Exception:
        pass

    # Heuristic: presence of error/unauthorized text
    try:
        body = driver.find_element(By.TAG_NAME, "body").text.lower()
        if any(x in body for x in ["unauthorized", "forbidden", "login", "sign in", "access denied"]):
            print("[AUTH] Page indicates auth required; cookies.json recommended.")
            return False
    except Exception:
        pass

    return True
