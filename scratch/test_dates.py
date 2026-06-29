import datetime

def test_comparison(today_str, lwd_str):
    print(f"Comparing today='{today_str}' and lwd='{lwd_str}'")
    print(f"today > lwd: {today_str > lwd_str}")

test_comparison("2026-05-06", "2026-05-06")
test_comparison("2026-05-07", "2026-05-06")
test_comparison("2026-05-06", "2026-05-07")
