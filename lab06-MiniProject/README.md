# Lab 06 - Mini Project: Weather Advisor TwoTier APIs

**Course:** ITMO 544 - Cloud Computing Technologies  
**Implementation:** Graduate Python Version

## Project Overview

This project implements a two-tier Weather Advisor application on AWS using Python and boto3.

The system contains:

- **Weather API** - retrieves weather information and stores cached results in PostgreSQL RDS.
- **Advisor API** - communicates with the Weather API through an Application Load Balancer and generates weather advice using the Gemini API.
- **Amazon RDS PostgreSQL** - private, encrypted database used for weather caching and history.
- **Application Load Balancer** - routes requests to the Weather and Advisor tiers.
- **Auto Scaling Groups and Launch Templates** - deploy and maintain the EC2 application instances.
- **AWS Systems Manager Parameter Store** - securely stores the database password and Gemini API key.

## Main Python Scripts

- `create_database.py` - creates the PostgreSQL database infrastructure.
- `delete_database.py` - removes the database and related resources.
- `create_weather_stack.py` - creates the Weather Advisor application infrastructure.
- `delete_weather_stack.py` - removes the Weather Advisor infrastructure.

## Testing

The project includes unit, integration, and chaos testing with `pytest`.

Final test results:

- **Unit tests:** 9 passed
- **Integration tests:** 7 passed
- **Chaos tests:** 2 passed
- `pytest -m "not integration and not chaos"`: **9 passed**

## Project Structure

```text
lab06-MiniProject/
├── advisor-app/
├── weather-app/
├── stack/
├── tests/
│   ├── unit/
│   └── integration/
├── create_database.py
├── delete_database.py
├── create_weather_stack.py
├── delete_weather_stack.py
├── pytest.ini
├── requirements.txt
└── GRADUATE_CHECKLIST.md
```

## Graduate Submission

See [`GRADUATE_CHECKLIST.md`](GRADUATE_CHECKLIST.md) for the Graduate Python Checklist, testing summary, Moto limitations, integration coverage, and Python-versus-Bash discussion.
