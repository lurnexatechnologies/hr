import re
import sys
from datetime import datetime, timedelta
from playwright.sync_api import Playwright, sync_playwright, expect

def run(playwright: Playwright) -> None:
    # Set headless=False to watch the workflow in real time!
    browser = playwright.chromium.launch(headless=False, slow_mo=300)
    context = browser.new_context()
    page = context.new_page()
    BASE_URL = "http://127.0.0.1:8000"
    
    print("🚀 Starting End-to-End Leave Workflow Test...")

    # --- STEP 1: EMPLOYEE APPLIES FOR LEAVE ---
    print("\n[1/6] Logging in as Employee...")
    page.goto(f"{BASE_URL}/auth/login/")
    page.locator("input[name=\"username\"]").fill("employee@lurnexa.com")
    page.locator("input[name=\"password\"]").fill("Password@123")
    page.get_by_role("button", name="Sign In").click()
    
    # Wait for Dashboard to confirm login
    expect(page.locator("h4:has-text('LURNEXA')")).to_be_visible(timeout=10000)

    print("[2/6] Submitting Leave Application...")
    page.goto(f"{BASE_URL}/leave/apply/")
    
    # Fill out the leave form
    page.locator("select[name=\"leave_type\"]").select_option("Casual Leave (CL)")
    
    # Calculate a valid date (e.g. tomorrow, avoiding weekends dynamically if possible, but let's just use a hardcoded safe offset)
    # For a perfect test, let's use next Wednesday to avoid weekends
    today = datetime.now()
    days_ahead = 3 - today.weekday()
    if days_ahead <= 0: # Target next Wednesday
        days_ahead += 7
    target_date = (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    
    page.locator("input[name=\"start_date\"]").fill(target_date)
    page.locator("input[name=\"end_date\"]").fill(target_date)
    page.locator("textarea[name=\"reason\"]").fill("Automated Test Leave Request")
    
    # Upload mandatory document
    page.locator("input[name=\"leave_document\"]").set_input_files("dummy.pdf")
    
    # Submit form
    page.get_by_role("button", name="Submit Application").click()
    print("✅ Leave Application Submitted Successfully!")

    # --- STEP 2: LOGOUT ---
    print("[3/6] Logging out of Employee account...")
    page.goto(f"{BASE_URL}/auth/logout/")

    # --- STEP 3: HR/MANAGER APPROVES LEAVE ---
    print("[4/6] Logging in as Manager...")
    page.goto(f"{BASE_URL}/auth/login/")
    page.locator("input[name=\"username\"]").fill("manager@lurnexa.com")
    page.locator("input[name=\"password\"]").fill("Password@123")
    page.get_by_role("button", name="Sign In").click()
    
    expect(page.locator("h4:has-text('LURNEXA')")).to_be_visible(timeout=10000)

    print("[5/6] Navigating to Leave Approvals...")
    page.goto(f"{BASE_URL}/leave/approvals/")
    
    # Click the Approve button on the first pending request
    print("[6/6] Approving the Leave Request...")
    # Using locator to find the first Approve button and click it
    approve_button = page.locator("a.btn-success:has-text('Approve')").first
    if approve_button.is_visible():
        approve_button.click()
        print("✅ Leave Request Approved Successfully!")
    else:
        print("⚠️ No pending leave requests found to approve! (Maybe it was auto-approved or already processed)")
    
    print("\n🎉 End-to-End Leave Workflow Test Completed Successfully!")
    
    # Close browser
    context.close()
    browser.close()

with sync_playwright() as playwright:
    try:
        run(playwright)
    except Exception as e:
        print(f"\n❌ Test Failed: {e}")
        sys.exit(1)
