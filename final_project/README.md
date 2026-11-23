# Final Project — Weather Advisor Application

Course: ITMO 544 Cloud Computing / Cloud Security

## Overview

Weather Advisor is a two-tier AWS application built with Python infrastructure code and Node.js Express services.

Users enter:
- a date within the next 7 days
- a 5-digit US ZIP code
- a clothing category
- an email address

The report shows Morning and Night values for temperature, wind, visibility, UV, humidity, rain, snow, road advice, dressing advice, and accessories.

## Architecture

Advisor tier:
- public form on ALB port 8080
- validates user input
- calls the Weather tier
- reads Gemini key from SSM
- generates and validates AI advice
- stores short-lived reports and Gemini call counters in DynamoDB
- handles SNS email delivery

Weather tier:
- internal service on ALB port 8081
- validates ZIP/date
- converts ZIP to coordinates
- calls weather APIs
- normalizes Morning/Night data
- derives Rain and Snow categories
- caches facts in DynamoDB

## Data Sources

- Zippopotam.us: ZIP to coordinates
- National Weather Service: primary US weather forecast source
- Open-Meteo: visibility, UV, humidity, precipitation, snowfall, timezone, and supported fallback values

Morning is 06:00-11:59 local time.
Night is 18:00-23:59 local time.

Weather facts come from APIs and application code. Gemini is used only for advice.

## Gemini

The Gemini key is stored in SSM Parameter Store.

Only the Advisor tier may read the key.

Gemini receives weather facts and the selected clothing category. The user's email address is never sent to Gemini.

Gemini returns structured advice for:
- road conditions
- dressing
- accessories

If Gemini fails or the daily call cap is reached, the application uses rule-based fallback advice.

## Email

Amazon SNS is used instead of SES.

Flow:
1. User clicks Email this report.
2. SNS sends a subscription confirmation the first time.
3. Recipient confirms the subscription.
4. User clicks Email this report again.
5. The report is delivered.

Each subscription has a recipient-specific filter policy so one user's report is not delivered to another subscriber.

## DynamoDB

Two PAY_PER_REQUEST tables are used:
- Weather facts table
- Advisor reports / Gemini counter table

TTL uses the `expires_at` attribute.

## Security

Separate IAM roles are used for Weather and Advisor.

Weather role:
- required DynamoDB access to the Weather facts table only

Advisor role:
- required DynamoDB access to the Advisor table
- SSM GetParameter for the Gemini key
- SNS Subscribe, Publish and ListSubscriptionsByTopic for the single project topic

Application port 3000 is reachable only from the ALB security group.

## Deployment

All deployment code is Python.

There are no `.sh` files and no Bash user-data.

Create the stack:

`python3 create_weather_stack.py`

Delete the stack:

`python3 delete_weather_stack.py`

The ALB DNS changes after the stack is deleted and recreated.

## Testing

Latest offline test result:

`9 passed, 9 deselected`

Live AWS tests completed successfully:
- Advisor health returned HTTP 200
- Weather health returned HTTP 200
- public form returned HTTP 200
- weather request returned Morning and Night facts
- report contained all ten required rows
- live report used Gemini advice
- SNS confirmation email arrived
- confirmed recipient received the actual Weather Advisor report
- delete script completed successfully
- stack recreated successfully

## Cost Control

The project uses:
- two small EC2 instances
- one ALB
- DynamoDB PAY_PER_REQUEST
- SSM standard parameter
- SNS email
- Gemini free-tier usage with a daily call cap

The stack is deleted when testing is complete.

## Presentation

1. Run `python3 create_weather_stack.py`.
2. Share the Advisor URL.
3. Allow classmates to test the form.
4. Show IAM and CloudTrail if requested.
5. Present design decisions and differences from earlier course work.
6. Run `python3 delete_weather_stack.py`.
7. Show that the project resources were removed.

## Main Files

- `advisor-app/`
- `weather-app/`
- `stack/`
- `tests/`
- `testing/`
- `create_weather_stack.py`
- `delete_weather_stack.py`
- `GRADUATE_CHECKLIST.md`
- `README.md`

## Reflection

The final design moved away from the older RDS-centered implementation and uses DynamoDB for short-lived application state. This works better with replaceable Auto Scaling instances.

SNS was selected instead of SES because SNS supports explicit recipient confirmation without requiring SES production access for arbitrary classroom recipients.

The system keeps weather facts, derived categories and AI advice separate. APIs provide facts, application code derives categories, and Gemini provides advice only.
