# Quick Browser Cookie Export Guide

Store cookie files under `.local/` (gitignored) to keep them out of version control.
Create it if needed: `mkdir .local`

## Method 1: Use EditThisCookie Extension (Easiest)

1. Install "EditThisCookie" extension for Chrome/Edge
2. Go to https://secure.123.net (while logged in)
3. Click the EditThisCookie icon
4. Click "Export" (bottom of popup)
5. Paste the output into a file called `.local/cookies.json`

## Method 2: Manual Cookie Export from DevTools

1. While logged into https://secure.123.net, press **F12**
2. Go to **Console** tab
3. Paste this code and press Enter:

```javascript
copy(JSON.stringify(
  document.cookie.split('; ').reduce((acc, cookie) => {
    const [name, value] = cookie.split('=');
    acc[name] = value;
    return acc;
  }, {}),
  null, 2
))
```

4. The cookies are now in your clipboard
5. Create a file called `.local/cookies.json` and paste:

```powershell
# In PowerShell
notepad .local\\cookies.json
# Then paste and save
```

## Method 3: Copy Specific Cookies

1. Press **F12** → **Application** tab → **Cookies** → **secure.123.net**
2. Look for these cookies and copy their values:
   - `session_id` or `PHPSESSID`
   - Any cookie with "auth" or "token" in the name
3. Create `.local/cookies.json`:

```json
{
  "PHPSESSID": "paste_value_here",
  "auth_token": "paste_value_here"
}
```

## Then Run the Session Scraper

```powershell
python webscraper/legacy/ticket_scraper_session.py `
  --customer CUSTOMER_HANDLE `
  --cookie-file .local/cookies.json
```

## Note About Cookie Expiration

Browser cookies typically expire after:
- Session cookies: When you close browser
- Persistent cookies: 1-30 days

You may need to re-export cookies periodically.
