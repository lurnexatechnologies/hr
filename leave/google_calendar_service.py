import requests
import datetime
import uuid
import logging
from core.dynamodb_service import HolidaysTable

logger = logging.getLogger(__name__)

# Official Google Public Holidays Calendar for India (software / tech sector standard in India)
GOOGLE_HOLIDAYS_ICS_URL = "https://calendar.google.com/calendar/ical/en.indian%23holiday%40group.v.calendar.google.com/public/basic.ics"

# Recognized official software company holidays in India
SOFTWARE_COMPANY_HOLIDAY_KEYWORDS = [
    "New Year",
    "Makar Sankranti",
    "Sankranti",
    "Pongal",
    "Republic Day",
    "Maha Shivratri",
    "Shivaratri",
    "Shivratri",
    "Holi",
    "Good Friday",
    "Ugadi",
    "Gudi Padwa",
    "Ram Navami",
    "Ambedkar Jayanti",
    "May Day",
    "Labour Day",
    "Eid",
    "Ramzan",
    "Bakrid",
    "Bonalu",
    "Independence Day",
    "Raksha Bandhan",
    "Rakhi",
    "Janmashtami",
    "Ganesh Chaturthi",
    "Vinayaka Chavithi",
    "Milad",
    "Onam",
    "Bathukamma",
    "Mahatma Gandhi",
    "Gandhi Jayanti",
    "Dussehra",
    "Dasara",
    "Vijayadashami",
    "Ayudha Puja",
    "Karwa Chauth",
    "Diwali",
    "Deepavali",
    "Kannada Rajyotsava",
    "Guru Nanak",
    "Christmas"
]

def sync_google_calendar_holidays():
    """
    Fetches official Indian public/software company holidays from Google Calendar's public iCal feed
    and automatically updates the DynamoDB HolidaysTable.
    """
    try:
        response = requests.get(GOOGLE_HOLIDAYS_ICS_URL, timeout=10)
        if response.status_code != 200:
            logger.warning(f"Could not fetch Google Calendar iCal feed. Status: {response.status_code}")
            return False

        ics_content = response.text
        existing_holidays = HolidaysTable.scan()
        existing_dates = {h.get('HolidayDate'): h for h in existing_holidays if h.get('HolidayDate')}

        current_year = datetime.datetime.now().year
        target_years = [str(current_year - 1), str(current_year), str(current_year + 1)]

        # Parse iCal content line-by-line
        events = []
        current_event = {}
        in_event = False

        for line in ics_content.splitlines():
            line = line.strip()
            if line == "BEGIN:VEVENT":
                in_event = True
                current_event = {}
            elif line == "END:VEVENT":
                if in_event and 'SUMMARY' in current_event and 'DTSTART' in current_event:
                    events.append(current_event)
                in_event = False
            elif in_event:
                if line.startswith("SUMMARY:"):
                    current_event['SUMMARY'] = line.replace("SUMMARY:", "").strip()
                elif line.startswith("DTSTART"):
                    # Format: DTSTART;VALUE=DATE:20260126 or DTSTART:20260126
                    parts = line.split(":")
                    if len(parts) > 1:
                        raw_date = parts[-1].strip()
                        if len(raw_date) >= 8:
                            current_event['DTSTART'] = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"


        added_count = 0
        for ev in events:
            date_str = ev.get('DTSTART')
            summary = ev.get('SUMMARY')

            if not date_str or not summary:
                continue

            # Limit sync to current and upcoming year
            if not any(date_str.startswith(y) for y in target_years):
                continue

            # Filter software company relevant holidays
            is_software_holiday = any(kw.lower() in summary.lower() for kw in SOFTWARE_COMPANY_HOLIDAY_KEYWORDS)
            if not is_software_holiday:
                continue

            if date_str not in existing_dates:
                holiday_item = {
                    'HolidayID': str(uuid.uuid4()),
                    'HolidayDate': date_str,
                    'Name': summary,
                    'Type': 'National',
                    'Description': summary
                }
                HolidaysTable.put_item(holiday_item)
                existing_dates[date_str] = holiday_item
                added_count += 1

        # Ensure standard software company holidays (Sankranti, Maha Shivaratri, Ugadi, etc.) are present
        cy = str(current_year)
        standard_software_holidays = [
            {"date": f"{cy}-01-14", "name": "Makar Sankranti / Pongal"},
            {"date": f"{cy}-01-26", "name": "Republic Day"},
            {"date": f"{cy}-02-15", "name": "Maha Shivaratri"},
            {"date": f"{cy}-03-04", "name": "Holi"},
            {"date": f"{cy}-03-19", "name": "Ugadi / Gudi Padwa"},
            {"date": f"{cy}-04-03", "name": "Good Friday"},
            {"date": f"{cy}-04-14", "name": "Dr. B.R. Ambedkar Jayanti"},
            {"date": f"{cy}-05-01", "name": "May Day / Labour Day"},
            {"date": f"{cy}-08-15", "name": "Independence Day"},
            {"date": f"{cy}-08-28", "name": "Raksha Bandhan"},
            {"date": f"{cy}-09-14", "name": "Ganesh Chaturthi / Vinayaka Chavithi"},
            {"date": f"{cy}-10-02", "name": "Mahatma Gandhi Jayanti"},
            {"date": f"{cy}-10-20", "name": "Dussehra / Vijayadashami"},
            {"date": f"{cy}-11-08", "name": "Diwali / Deepavali"},
            {"date": f"{cy}-12-25", "name": "Christmas"}
        ]

        for sh in standard_software_holidays:
            if sh["date"] not in existing_dates:
                h_item = {
                    'HolidayID': str(uuid.uuid4()),
                    'HolidayDate': sh["date"],
                    'Name': sh["name"],
                    'Type': 'National',
                    'Description': sh["name"]
                }
                HolidaysTable.put_item(h_item)
                existing_dates[sh["date"]] = h_item
                added_count += 1

        logger.info(f"Google Calendar Holiday Sync Completed. Added {added_count} new holidays.")
        return True

    except Exception as e:
        logger.error(f"Error syncing Google Calendar holidays: {e}")
        return False
