# Calendar Feature Guide

**New in this update:** Automatic calendar reminders for trade exits + visual upcoming exits panel on Home page.

---

## Feature 1: Calendar Export (.ics files)

### What it does
When you log a new trade in the Trade Journal, you can download a calendar reminder that imports directly into your calendar app.

### How to use it

1. **Go to Trade Journal** → Log a new trade (practice or real)
2. **After adding the trade**, you'll see a success message with:
   - "Suggested exit date" input (defaults to 90 days from entry)
   - "📅 Download calendar reminder (.ics)" button
3. **Adjust the exit date** if needed (e.g., if Forward Outlook suggests a different hold window)
4. **Click the download button** → saves a `.ics` file
5. **Open the .ics file** → your calendar app imports it automatically
6. **Done!** You'll get a notification on the exit date at 9 AM

### Supported calendar apps
- ✅ Google Calendar (desktop and mobile)
- ✅ Apple Calendar (Mac, iPhone, iPad)
- ✅ Outlook (desktop, web, mobile)
- ✅ Any calendar app that supports ICS/iCal format

### What the reminder includes
- **Event title:** "TRADEON: Exit [TICKER]"
- **Date:** The exit date you specified (all-day event)
- **Alarm:** 9 AM on the exit date
- **Description:**
  - Ticker and company name
  - Entry date and price
  - Shares and capital invested
  - Trade ID (for matching back to Journal)
  - Practice tag if it's a paper trade

### Example workflow

**Step 1:** Log trade in Journal
```
Ticker: CBA.AX
Buy date: 21 Apr 2026
Buy price: A$125.50
Shares: 10
```

**Step 2:** Download calendar reminder
- Suggested exit: 21 Jul 2026 (90 days)
- Click "Download calendar reminder"

**Step 3:** Import to calendar
- Open `tradeon_CBA.AX_T0001.ics` on your device
- Calendar app opens automatically
- Click "Add to calendar"

**Step 4:** Get reminded
- On 21 Jul 2026 at 9 AM, you get a notification
- Open TRADEON → Trade Journal
- Close the trade with your actual exit price

---

## Feature 2: Upcoming Exits Panel (Home Page)

### What it does
Shows all open trades that have an exit date in the next 30 days, sorted by urgency, right on the Home page.

### Where to find it
- Open TRADEON → **Home** page
- Look for "📅 Upcoming trade exits" section
- Appears automatically if you have open trades

### Color coding

| Color | Meaning | When |
|-------|---------|------|
| 🔴 Red | ⚠️ EXIT TODAY | Exit date is today or past |
| 🟠 Orange | ⏰ Tomorrow | Exit date is tomorrow |
| 🟡 Yellow | 📌 2-3 days | Exit in 2-3 days |
| 🟢 Green | ✓ 4-7 days | Exit in 4-7 days |
| 🔵 Blue | 8-30 days | Exit in 8-30 days |

### What it shows
For each trade:
- **Ticker** (with 📝 if practice trade)
- **Urgency** (days until exit)
- **Exit date** (formatted: Mon 21 Jul)
- **Entry details** (price x shares)
- **Trade ID** (for quick lookup in Journal)

### Example

```
CBA.AX - ⏰ Tomorrow
Exit: Tue 22 Apr | Entry: A$125.50 x 10 shares | Trade ID: T0001

WES.AX 📝 - ✓ 5 days
Exit: Sun 27 Apr | Entry: A$48.20 x 20 shares | Trade ID: T0002

JPM - 12 days
Exit: Fri 03 May | Entry: A$215.30 x 5 shares | Trade ID: T0003
```

### Notes
- **Top 5 most urgent** shown by default
- If more than 5, shows count of remaining: "+ 3 more exits beyond 30 days"
- **Exit dates estimated** as 90 days from entry (you can customize by logging actual exit dates)
- Only shows trades with exits in **next 30 days** (beyond that is too far out)

---

## Pro Tips

### Tip 1: Set exit date from Forward Outlook
When Forward Outlook shows a GO signal, it suggests a specific exit date based on the hold window. Use that date when downloading your calendar reminder instead of the default 90 days.

### Tip 2: Check Home page daily
Make it your routine:
1. Open TRADEON
2. Check "Upcoming Exits" on Home
3. If any are red/orange → review those trades today

### Tip 3: Practice trades get reminders too
Even practice trades show in the calendar and upcoming exits panel (marked with 📝). This helps you build the habit of checking exit dates.

### Tip 4: Multiple devices
Download the .ics file on your laptop, open it, and it syncs to your phone via cloud calendar (Google/Apple/Outlook). You get the notification wherever you are.

### Tip 5: Adjust reminder time
After importing the .ics file, you can edit the event in your calendar app to:
- Change the alarm time (default is 9 AM)
- Add multiple reminders (e.g., 1 day before + day-of)
- Add notes or links

---

## Troubleshooting

**Q: I downloaded the .ics file but nothing happened**
A: Try:
1. Open your calendar app first
2. Look for "Import" or "Add from file"
3. Browse to the downloaded .ics file
4. Select it manually

**Q: The Upcoming Exits panel is empty but I have open trades**
A: The panel only shows exits in the next 30 days. If all your trades have exits beyond 30 days, it'll show "No trades nearing exit in the next 30 days."

**Q: Exit date is wrong**
A: The app estimates 90 days from entry. To fix:
- When you download the calendar reminder, adjust the "Suggested exit date" input before clicking download
- Or edit the event in your calendar app after importing

**Q: Can I download calendar reminders for old trades?**
A: Currently, the download button only appears right after adding a new trade. For existing trades, the Upcoming Exits panel on Home is your visual reminder.

**Q: Practice trade 📝 emoji doesn't show in my calendar**
A: The emoji is in the description field of the calendar event. Some calendar apps show it, others don't - this doesn't affect the functionality.

---

## Future Enhancements (not yet implemented)

Ideas for future versions:
- Batch export: Download all open trades as one .ics file
- Email reminders: Optional email notification 1 day before exit
- SMS reminders: Text message notification (would need phone number)
- In-app notifications: Browser push notifications when app is open
- Custom reminder times: Choose your preferred alarm time when downloading
- Calendar page: Visual calendar view of all exits

---

## Summary

**Two ways to never miss an exit:**

1. **📅 Download calendar reminder** (Trade Journal page)
   - One .ics file per trade
   - Imports to your calendar app
   - Get notification on exit date

2. **🏠 Check Upcoming Exits** (Home page)
   - Visual at-a-glance panel
   - Color-coded by urgency
   - Always up-to-date when you open the app

**No more copying to your other calendar - it's automatic now!**
