import os
import datetime
import logging
from datetime import timedelta
from openai import OpenAI
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# Configure logging to output to a file with timestamp and log level
logging.basicConfig(
    filename="reminder.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

client = OpenAI()

# ID of your calendar to add the reminder event to, can be found in Google Calendar UI
YOUR_CALENDAR_ID = ""
# ID of friends calendar to scan
OTHER_CALENDAR_ID = ""
# Text to add before the list of important events in the reminder event added to your calendar
REMINDER_PREPEND = ""
SCOPES = ["https://www.googleapis.com/auth/calendar"]

PATH_TO_TOKEN = ""
PATH_TO_CREDENTIALS = ""


def authenticate_google_calendar():
    creds = None
    if os.path.exists(PATH_TO_TOKEN):
        creds = Credentials.from_authorized_user_file(PATH_TO_TOKEN, SCOPES)
        logging.info("Loaded credentials from token.json")
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                logging.info("Credentials refreshed successfully")
            except Exception as e:
                logging.error("Error refreshing credentials: %s", str(e))
        else:
            flow = InstalledAppFlow.from_client_secrets_file(PATH_TO_CREDENTIALS, SCOPES)
            creds = flow.run_local_server(port=0)
            logging.info("Alternative credentials refresh?")
        with open(PATH_TO_TOKEN, "w") as token:
            token.write(creds.to_json())
            logging.info("Saved credentials to token.json")
    service = build("calendar", "v3", credentials=creds)
    return service


def fetch_events(service, calendar_id, time_min, time_max):
    try:
        events_result = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = events_result.get("items", [])
        logging.info("Fetched %d events from calendar %s", len(events), calendar_id)
        return events
    except Exception as e:
        logging.error("Error fetching events: %s", str(e))
        return []


PROMPT = """Analyse the following list of calendar event names and identify which events are thoughtful to mention in conversation. Prioritise events that suggest personal milestones, self-care, noticeable changes, or moments of significance. Exclude overly routine and generic activities unless they indicate something special or unique. If all events are routine and none fit the criteria, respond with "None". Only output a concise list of the identified events.

Example Input: Haircut, Lecture 1, Do washing, Lecture 2
Example Output: Haircut

Example Input: Do washing, Grocery shopping, Lecture 1
Example Output: None"""


def extract_events(events_list):
    try:
        response = client.responses.create(
            model="gpt-4o-mini",
            temperature=0.2,
            top_p=0.1,
            instructions=PROMPT,
            input=events_list,
        )
        extracted_text = response.output_text
        logging.info("Extracted events: %s", extracted_text)
    except Exception as e:
        extracted_text = f"Error extracting events: {str(e)}"[:1024]
        logging.error("Error in extract_events: %s", str(e))
    return extracted_text


def create_reminder_event(service, calendar_id, day, events_text):
    start_datetime = datetime.datetime.combine(day, datetime.time(9, 30))
    end_datetime = start_datetime + timedelta(minutes=30)
    events_count = len(events_text.split(","))
    new_event = {
        "summary": f"⚠️ {events_count} Reminder{'s' if events_count > 1 else ''}",
        "description": f"{REMINDER_PREPEND}{events_text}",
        "start": {
            "dateTime": start_datetime.isoformat(),
            "timeZone": "UTC",
        },
        "end": {
            "dateTime": end_datetime.isoformat(),
            "timeZone": "UTC",
        },
    }
    try:
        event = (
            service.events().insert(calendarId=calendar_id, body=new_event).execute()
        )
        logging.info(
            "Created reminder in calendar %s with event ID %s on %s",
            calendar_id,
            event.get("id"),
            day,
        )
    except Exception as e:
        logging.error("Error creating reminder event: %s", str(e))
        event = None
    return event


if __name__ == "__main__":
    logging.info("==Calendar Scanner started==")
    service = authenticate_google_calendar()

    now = datetime.datetime.now()
    tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
        days=1
    )
    time_min = tomorrow.isoformat() + "Z"
    time_max = (tomorrow + timedelta(days=1)).isoformat() + "Z"

    events = fetch_events(service, OTHER_CALENDAR_ID, time_min, time_max)
    events_list = []
    for event in events:
        start_str = event.get("start", {}).get(
            "dateTime", event.get("start", {}).get("date")
        )
        try:
            start_dt = datetime.datetime.fromisoformat(start_str.rstrip("Z"))
        except Exception as e:
            logging.error("Skipping event due to parsing error: %s", str(e))
            continue
        event_summary = event.get("summary", None)
        if event_summary:
            events_list.append(event_summary)

    if events_list:
        events_formatted = ",".join(events_list)
        events_text = extract_events(events_formatted)
        events_text = events_text.replace('"', "").strip()
        if events_text:
            if events_text.lower() != "none":
                reminder_event = create_reminder_event(
                    service, YOUR_CALENDAR_ID, now.date(), events_text
                )
        else:
            logging.error("Error from LLM output: %s", events_text)
    else:
        logging.info("No important events identified tomorrow")

    logging.info("Finished, have a nice day")
