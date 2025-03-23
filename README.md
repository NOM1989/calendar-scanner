## Calendar Scanner

Forgetful?

This script scans a given Google Calendar (you must have access to it) and uses an LLM to extract potentially important events. It then inserts an event into **your** calendar the day before, listing the identified events.

The intended use case is to remind you of important events in a friend's calendar the day before they happen.

### Installation
You will have to set up an OpenAI API key in addition to a Google Project with the Calendar scope to give it access to your calendar(s).

Set up a cron job to run this script each morning.