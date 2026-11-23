# Graduate Final Project Checklist — Weather Advisor

## Application

- [x] Public Advisor web form
- [x] Date limited to the next seven days
- [x] Five-digit US ZIP validation
- [x] Clothing category selection
- [x] Email address validation
- [x] Morning period: 06:00-11:59 local time
- [x] Night period: 18:00-23:59 local time
- [x] Temperature
- [x] Wind speed
- [x] Visibility
- [x] UV index
- [x] Humidity
- [x] Rain category: Heavy / Mild / No
- [x] Snow category: Heavy / Mild / No
- [x] Suggested road conditions
- [x] Suggested dressing
- [x] Suggested accessories

## Weather Data

- [x] Zippopotam.us converts ZIP to coordinates
- [x] National Weather Service is the primary US forecast source
- [x] Open-Meteo fills required weather-data gaps
- [x] Morning and Night are evaluated in the ZIP location's timezone
- [x] Weather facts are kept separate from Gemini advice
- [x] Missing NWS values may fall back to Open-Meteo
- [x] Missing values are not silently treated as zero
- [x] Recent DynamoDB facts cache can be used when an upstream service fails

## Gemini

- [x] Gemini API key stored in SSM Parameter Store
- [x] Advisor tier alone may read the Gemini parameter
- [x] Gemini receives weather facts and clothing category only
- [x] Email address is never sent to Gemini
- [x] Structured Morning/Night advice is validated
- [x] Rule-based fallback is used when Gemini is unavailable
- [x] Daily Gemini call cap stored atomically in DynamoDB

## Email

- [x] Amazon SNS selected instead of SES
- [x] One SNS topic created by the Python stack
- [x] Recipient must confirm email subscription
- [x] Recipient-specific filter policy prevents cross-recipient delivery
- [x] Confirmed recipient receives the requested plain-text report
- [x] Tested successfully with multiple email providers
- [x] Per-visitor email request limit included

## DynamoDB

- [x] Weather facts table
- [x] Advisor saved-report / Gemini-counter table
- [x] PAY_PER_REQUEST billing mode
- [x] TTL enabled using `expires_at`
- [x] Weather role accesses only the facts table
- [x] Advisor role accesses only the Advisor table

## AWS Infrastructure

- [x] Two application tiers
- [x] Application Load Balancer
- [x] Advisor listener on port 8080
- [x] Weather listener on port 8081
- [x] Separate target groups
- [x] Separate Auto Scaling Groups
- [x] Separate IAM roles and instance profiles
- [x] Application instances accept port 3000 only from the ALB security group
- [x] Public URL tested successfully
- [x] Both `/health` endpoints returned HTTP 200

## Python Deployment

- [x] All AWS deployment code is Python
- [x] EC2 boot script is Python
- [x] No `.sh` files remain
- [x] No Bash user-data
- [x] Weather and Advisor user-data remain below EC2's 16 KB limit
- [x] Create script builds the complete stack
- [x] Delete script removes the complete stack
- [x] Target-group deletion retries while AWS finishes detaching listeners
- [x] Cleanup tested successfully on the first retry-safe run

## Testing Evidence

- [x] `node --check weather-app/app.js`
- [x] `node --check advisor-app/app.js`
- [x] Offline pytest suite: **9 passed, 9 deselected**
- [x] Advisor `/health`: HTTP 200
- [x] Weather `/health`: HTTP 200
- [x] Real Weather request returned Morning/Night facts
- [x] Real Advisor report returned all ten required rows
- [x] Gemini advice verified in live report
- [x] SNS subscription confirmation verified
- [x] Actual Weather Advisor report successfully delivered by SNS
- [x] Public Advisor URL loaded successfully

## Presentation Preparation

For the live presentation:

1. Run `python3 create_weather_stack.py`.
2. Share the Advisor URL printed by the script.
3. Allow classmates to submit reports for five minutes.
4. Be ready to show IAM roles/policies and CloudTrail.
5. Explain design changes and decisions.
6. Run `python3 delete_weather_stack.py`.
7. Show that the project resources were removed.

The ALB DNS name changes after the stack is deleted and recreated, so always use the current URL printed by `create_weather_stack.py`.
