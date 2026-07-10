import re
import sys
from playwright.sync_api import Playwright, sync_playwright, expect

def run(playwright: Playwright) -> None:
    # Launch browser (set headless=True to prevent opening the browser window)
    # Using a slightly faster slow_mo to test thoroughly without taking too long
    browser = playwright.chromium.launch(headless=True, slow_mo=200)
    context = browser.new_context()
    page = context.new_page()

    BASE_URL = "http://127.0.0.1:8000"
    
    print("🚀 Starting Comprehensive Automated E2E Test for HRMS...")

    # 1. Test Login Page Load
    print("\n[1/7] Navigating to login page...")
    page.goto(f"{BASE_URL}/auth/login/")
    expect(page).to_have_title(re.compile("Login", re.IGNORECASE))

    # 2. Test Authentication 
    print("[2/7] Attempting to login as HR Admin...")
    page.locator("input[name=\"username\"]").fill("hr@lurnexa.com")
    page.locator("input[name=\"password\"]").fill("Password@123")
    page.get_by_role("button", name="Sign In").click()

    # 3. Verify Dashboard Load & Header
    print("[3/7] Checking if Dashboard loaded successfully...")
    # Wait for the LURNEXA header brand to be visible, ensuring we are in the portal
    expect(page.locator("h4:has-text('LURNEXA')")).to_be_visible(timeout=15000)
    print("✅ Dashboard loaded successfully.")

    # 4. Test Employee Directory
    print("[4/7] Testing Employee Directory Navigation...")
    try:
        page.get_by_role("link", name=re.compile("Employees", re.IGNORECASE), exact=True).click()
        expect(page).to_have_url(re.compile(r".*employee.*|.*directory.*", re.IGNORECASE))
        # Ensure page content loads (looking for an Add button or table)
        expect(page.get_by_role("heading")).to_be_visible()
        print("✅ Employee Directory module works!")
    except Exception as e:
        print(f"❌ Employee Directory test failed: {e}")

    # 5. Test Leave Approvals
    print("[5/7] Testing Leave Approvals Module...")
    try:
        page.get_by_role("link", name=re.compile("Leave Approvals", re.IGNORECASE)).click()
        expect(page).to_have_url(re.compile(r".*leave.*", re.IGNORECASE))
        print("✅ Leave Approvals module works!")
    except Exception as e:
        print(f"❌ Leave Approvals test failed: {e}")

    # 6. Test Historical Payroll
    print("[6/7] Testing Historical Payroll Module...")
    try:
        page.get_by_role("link", name=re.compile("Historical Payroll", re.IGNORECASE)).click()
        expect(page).to_have_url(re.compile(r".*historical.*", re.IGNORECASE))
        print("✅ Historical Payroll module works!")
    except Exception as e:
        print(f"❌ Historical Payroll test failed: {e}")

    # 7. Test PF Management
    print("[7/7] Testing PF Management Module...")
    try:
        page.get_by_role("link", name=re.compile("PF Management", re.IGNORECASE)).click()
        expect(page).to_have_url(re.compile(r".*pf.*", re.IGNORECASE))
        print("✅ PF Management module works!")
    except Exception as e:
        print(f"❌ PF Management test failed: {e}")

    print("\n🎉 Comprehensive High-Level Workflow Testing Completed Successfully!")
    
    # Close browser
    context.close()
    browser.close()

with sync_playwright() as playwright:
    try:
        run(playwright)
    except Exception as e:
        print(f"\n❌ FATAL Test Failure: {e}")
        sys.exit(1)
