import os
import sys
from selenium import webdriver
from selenium.webdriver.chrome.options import Options


def main():
    opts = Options()
    opts.add_argument('--headless=new')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--no-sandbox')

    chrome_path = os.environ.get('CHROME_PATH')
    if chrome_path and os.path.exists(chrome_path):
        opts.binary_location = chrome_path
        print(f'Using Chrome binary: {chrome_path}')
    else:
        print('Using system Chrome (PATH/installed)')

    try:
        driver = webdriver.Chrome(options=opts)
        driver.get('https://example.com')
        print('Title:', driver.title)
        driver.quit()
        print('Selenium headless OK')
        return 0
    except Exception as e:
        print('Selenium error:', e)
        return 1


if __name__ == '__main__':
    sys.exit(main())
