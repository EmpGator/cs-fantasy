# FantasyGator

A Counter-Strike 2 fantasy pick'em platform that replaces the traditional Google Sheets approach with a proper web application.

## Features

- **Swiss Stage Predictions** - Predict team records (3-0, 3-1, etc.) with configurable limits
- **Bracket Predictions** - Predict match winners and scores in playoff brackets
- **Stat Predictions** - Predict tournament MVPs, top fraggers, and other player statistics
- **HLTV Integration** - Automatic parsing of tournament data, teams, players, and results
- **Scoring Engine** - Flexible JSON-based scoring rules for different prediction types
- **Leaderboards** - Track user rankings across tournaments and modules
- **Admin Wizard** - Step-by-step tournament creation from HLTV URLs

## Tech Stack

- Python / Django
- PostgreSQL
- Alpine.js
- Django-Q2 (background tasks)
- Bootstrap

## Development Setup

```bash
# Clone and setup
git clone <repo>
cd cs-fantasy
pip install -r requirements.txt

# Database
createdb cs_fantasy
python manage.py migrate
python manage.py initialize_defaults

# Run
python manage.py runserver
python manage.py qcluster  # Background task worker
```

## Future Plans

- Email notifications for prediction deadlines
- Tournament standings visualization
- Historical statistics and trends
- Mobile-optimized UI improvements

## Deployment

Deployment is handled via Coolify with CI/CD integration. Production configuration details to be added.
