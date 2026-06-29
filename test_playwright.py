from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('http://localhost:8000/auth/login/')
    page.fill('input[name="email"]', 'hr@lurnexa.com')
    page.fill('input[name="password"]', 'Password@123')
    page.click('button[type="submit"]')
    page.wait_for_url('**/dashboard/')
    
    page.goto('http://localhost:8000/attendance/hr_attendance/')
    print('Initial date in DOM:', page.locator('#datePicker').evaluate('el => el.value'))
    print('Initial URL:', page.url)
    
    # Register console logger to see JS errors
    page.on('console', lambda msg: print(f"Browser Console: {msg.text}"))
    
    try:
        page.evaluate('''() => {
            const el = document.getElementById('datePicker');
            el.value = '2026-05-04';
            const evt = new Event('change', { bubbles: true });
            el.dispatchEvent(evt);
        }''')
        # Wait a bit
        page.wait_for_timeout(2000)
        print('Date after JS dispatch:', page.locator('#datePicker').evaluate('el => el.value'))
        print('URL after JS dispatch:', page.url)
    except Exception as e:
        print('Error during JS execution:', e)
    browser.close()
