# Project Support FAQ

## Demo login

For the local recruiter demo, set `DEMO_ADMIN_EMAIL` and `DEMO_ADMIN_PASSWORD` in the project `.env` file. Run `python -m src.cli seed-demo`, then start the app with `python app.py` and open `http://localhost:5000`. The development login screen shows the configured values. If sign-in fails, check that both settings are present and match the demo account in the local database, then restart the app. The hosted environment uses a separate database and credentials.

## App will not start

Run commands from the project root. Install dependencies with `pip install -r requirements.txt`, then run `python app.py`. The app binds to `FLASK_HOST` and `FLASK_PORT` (default `127.0.0.1:5000`); when `FLASK_PORT` is unset it honors `PORT`. If the preferred port is busy, development startup picks the next available port and prints its `http://localhost:<port>/` URL. Open that exact URL; the browser opens it automatically unless `OPEN_BROWSER=false`. The UI serves directly from `frontend/src` in development without requiring a build.

## Predictions and routing

Open a ticket and choose `Assess SLA risk` (formerly labeled `Predict SLA`). The same configured policy is used for the displayed status and saved assessment. It compares priority and elapsed ticket age against the target and warning window, then explains the result. Defaults are examples: set `SLA_TARGET_CRITICAL_HOURS`, `SLA_TARGET_HIGH_HOURS`, `SLA_TARGET_MEDIUM_HOURS`, `SLA_TARGET_LOW_HOURS`, and `SLA_WARNING_FRACTION_PERCENT` in `.env` to match an approved service policy. Ticket text and actual outcomes are not prediction inputs. Team routing is manual because this project has no validated routing model. ML lab candidates use synthetic development data and remain comparison-only.

## Mock JIRA import

Use the `JIRA` page to import a Jira-shaped sample issue. This is a local mock integration and does not connect to Atlassian. Reimporting the same issue key updates the corresponding local ticket rather than creating a duplicate.

## Roles and user administration

The demo administrator can manage users from `User administration`. Admins can manage tickets, analytics, mock JIRA imports, and users. Analysts can review tickets, prediction history, and analytics. Support agents can work with tickets and request predictions. A `403` response means the signed-in role does not have access to that action.

## ML lab and candidate models

Open `ML lab` while signed in to view candidate model status, training commands, and evaluation notes. If candidates are unavailable, run the documented training commands from the project root. Candidate results are experimental and are not written to baseline ticket prediction history.
