<div align="center">

# Ã°Å¸Å½Â« AI-Powered Ticket Routing & SLA Breach Prediction

<p align="center">
  <img src="https://readme-typing-svg.demolab.com?font=Poppins&weight=600&size=28&duration=3000&pause=1000&color=00C2FF&center=true&vCenter=true&width=900&lines=AI-Powered+Ticket+Routing;SLA+Breach+Prediction;Machine+Learning+%2B+Flask+REST+API;Python+%7C+Scikit-Learn+%7C+Random+Forest" alt="Typing Animation"/>
</p>

<p align="center">

![Python](https://img.shields.io/badge/Python-3.x-blue?style=for-the-badge&logo=python)
![Flask](https://img.shields.io/badge/Flask-REST_API-black?style=for-the-badge&logo=flask)
![Scikit-Learn](https://img.shields.io/badge/Scikit--Learn-ML-orange?style=for-the-badge&logo=scikitlearn)
![Pandas](https://img.shields.io/badge/Pandas-Data_Processing-150458?style=for-the-badge&logo=pandas)
![Joblib](https://img.shields.io/badge/Joblib-Model_Serialization-success?style=for-the-badge)

</p>

<p align="center">

![GitHub stars](https://img.shields.io/github/stars/Ganeshbasani/AI-Powered-Ticket-Routing?style=social)
![GitHub forks](https://img.shields.io/github/forks/Ganeshbasani/AI-Powered-Ticket-Routing?style=social)
![GitHub last commit](https://img.shields.io/github/last-commit/Ganeshbasani/AI-Powered-Ticket-Routing)
![License](https://img.shields.io/badge/License-MIT-green)

</p>

---

### Ã°Å¸Å¡â‚¬ Intelligent Ticket Routing using Machine Learning

Predicts a prototype **SLA breach-risk label** and presents a transparent baseline team recommendation for tickets managed through a Flask REST API and product frontend.

</div>

---

## ðŸš€ Live Demo â€” Recruiter Access

### ðŸŒ Try the Application

**Live Demo:** https://ai-powered-ticket-routing-system.onrender.com

> **Demo Login**
>
> **Demo ID:** Demo@gmail.com
>
> **Password:** Demo@1234
>
> This dedicated demo account lets recruiters and reviewers explore the deployed application.

### ðŸ–¥ï¸ Application UI Showcase

#### ðŸ“Š Operations Dashboard
![Operations Dashboard](docs/screenshots/dashboard.png)

#### ðŸŽ« Ticket Management
![Ticket Management](docs/screenshots/tickets.png)

#### ðŸ¤– SLA Prediction History
![Prediction History](docs/screenshots/predictions.png)

#### ðŸ“ˆ Analytics Dashboard
![Analytics Dashboard](docs/screenshots/analytics.png)

---

# 🚀 Live Demo — Recruiter Access

### 🌐 Try the Deployed Application

**Live Demo:** https://ai-powered-ticket-routing-system.onrender.com

> ### 🔐 Demo Credentials
> **Demo ID:** `Demo@gmail.com`  
> **Password:** `Demo@1234`

Explore the deployed ticket-management, automatic prediction, prediction-history, and analytics workflows.

## 🖥️ Product UI Showcase

### 📊 Operations Dashboard
![Operations Dashboard](docs/screenshots/dashboard.png)

### 🎫 Ticket Management
![Ticket Management](docs/screenshots/tickets.png)

### 🤖 SLA Prediction History
![SLA Prediction History](docs/screenshots/predictions.png)

### 📈 Analytics Dashboard
![Analytics Dashboard](docs/screenshots/analytics.png)

---
## Production API Contract

## Security and Administration

Authentication uses expiring bearer tokens obtained from `POST /api/v1/auth/login`.
Administrators manage users through the protected `/api/v1/users` endpoints;
analysts have read-only ticket access, and support agents can create tickets and
request predictions. Disabled accounts cannot log in or use existing tokens.

Bootstrap the first administrator locally with `BOOTSTRAP_ADMIN_EMAIL` and
`BOOTSTRAP_ADMIN_PASSWORD` set, then run `python -m src.cli bootstrap-admin`.
The command refuses to overwrite an existing administrator. Login, prediction,
and mock-JIRA import use configurable single-instance rate limits; requests are
limited to 1 MB. See [security and operations](docs/security.md) for complete
role, audit, header, and mock-JIRA guidance.

`GET /api/v1/health` reports process liveness. `GET /api/v1/ready` reports
whether a valid model artifact is immediately available and returns `503` until
it is. Every response has an `X-Request-ID` header and a matching `request_id`
field. Invalid requests return a stable `validation_error` object; unexpected
errors return a generic `internal_error` response without implementation details.

`POST /api/v1/predict` accepts exactly `priority` and `created_hours`. The
response includes the binary risk label, existing routing heuristic, model
version, and request ID. It deliberately does not expose an uncalibrated model
probability.

## Configuration, Docker, and CI

Copy `.env.example` to `.env` for local overrides. `APP_ENV`, `FLASK_PORT`,
`FLASK_DEBUG`, `LOG_LEVEL`, `MODEL_PATH`, and `DATA_PATH` are validated at
startup. Model and data paths must stay inside the application directory.

Run locally with `python app.py`; run checks with `python -m compileall -q src
tests` and `python -m pytest -q`.

Build and run the production container with:

```bash
docker build -t sla-ticket-routing .
docker run --rm -p 5000:5000 --env-file .env sla-ticket-routing
```

The Docker image uses a non-root user and stdout JSON logging. GitHub Actions
runs compilation and tests on pushes and pull requests.

See [product workflows](docs/product.md), [platform API](docs/platform.md), and
[security and operations](docs/security.md) for the implemented roles, ticket
lifecycle, analytics, mock-JIRA boundary, and administrative endpoints.

## Dataset Foundation

The data layer now canonicalizes CSV, JSON, and SQLite ticket exports, validates
them without silently dropping records, flags leakage-prone columns, and can
produce reproducible Markdown profiles. See the [dataset contract](docs/dataset_contract.md)
and the generated [prototype profile](docs/dataset_profile.md). This does not
change the current model: the bundled three-record dataset remains insufficient
for meaningful ML evaluation.

---

# Ã°Å¸â€œÅ’ Table of Contents

- Overview
- Features
- Tech Stack
- Project Architecture
- Folder Structure
- Installation
- Running the Application
- API Documentation
- Example Request
- Machine Learning Workflow
- Running Tests
- Future Improvements
- License

---

# Ã°Å¸â€œâ€“ Overview

Managing support tickets efficiently is critical for reducing response times and maintaining Service Level Agreements (SLAs).

This project demonstrates how Machine Learning can assist ticket management by predicting whether a ticket is likely to breach its SLA while also recommending the appropriate routing team.

The project is implemented as a backend-focused prototype with a REST API built using Flask.

---

# Ã¢Å“Â¨ Features

Ã¢Å“â€¦ Predict SLA Breach Risk

Ã¢Å“â€¦ Intelligent Ticket Routing

Ã¢Å“â€¦ REST API using Flask

Ã¢Å“â€¦ Random Forest Machine Learning Model

Ã¢Å“â€¦ Automatic Model Training

Ã¢Å“â€¦ Health Check Endpoint

Ã¢Å“â€¦ Clean Project Structure

Ã¢Å“â€¦ Automated Unit Testing

---

# Ã°Å¸â€ºÂ  Tech Stack

| Category | Technology |
|-----------|------------|
| Language | Python |
| Backend | Flask |
| Machine Learning | Scikit-Learn |
| Data Processing | Pandas |
| Model Storage | Joblib |
| Testing | Pytest |

---

# Ã°Å¸Â§Â  Project Architecture

```text
                Ticket Data
                     Ã¢â€â€š
                     Ã¢â€“Â¼
              Data Preprocessing
                     Ã¢â€â€š
                     Ã¢â€“Â¼
          Random Forest Training
                     Ã¢â€â€š
             Saved ML Model
                     Ã¢â€â€š
                     Ã¢â€“Â¼
             Flask REST API
                     Ã¢â€â€š
                     Ã¢â€“Â¼
        SLA Prediction + Team Routing
```

---

# Ã°Å¸â€œâ€š Project Structure

```text
AI-Powered-Ticket-Routing
Ã¢â€â€š
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ api/
Ã¢â€â€š
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ data/
Ã¢â€â€š   Ã¢â€â€Ã¢â€â‚¬Ã¢â€â‚¬ tickets.csv
Ã¢â€â€š
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ docs/
Ã¢â€â€š
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ ml_model/
Ã¢â€â€š
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ src/
Ã¢â€â€š
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ tests/
Ã¢â€â€š
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ app.py
Ã¢â€â€š
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ requirements.txt
Ã¢â€â€š
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ requirements-dev.txt
Ã¢â€â€š
Ã¢â€â€Ã¢â€â‚¬Ã¢â€â‚¬ README.md
```

---

# Ã¢Å¡â„¢Ã¯Â¸Â Installation

## Clone Repository

```bash
git clone https://github.com/Ganeshbasani/AI-Powered-Ticket-Routing.git

cd AI-Powered-Ticket-Routing
```

---

## Create Virtual Environment

### Windows

```bash
python -m venv venv

venv\Scripts\activate
```

### Linux / macOS

```bash
python3 -m venv venv

source venv/bin/activate
```

---

## Install Dependencies

```bash
pip install -r requirements.txt
```

---

# Ã¢â€“Â¶Ã¯Â¸Â Run the Application

```bash
python app.py
```

Server starts at

```
http://127.0.0.1:5000
```

---

# Ã°Å¸Å’Â REST API

## Health Check

```
GET /api/v1/health
```

Response

```json
{
    "status":"ok"
}
```

---

## Predict Ticket

```
POST /api/v1/predict
```

Example Request

```json
{
    "priority":"High",
    "created_hours":8
}
```

Example Response

```json
{
    "assigned_team":"L2",
    "sla_breach_risk":"High"
}
```

---

# Ã°Å¸Â¤â€“ Machine Learning Workflow

```text
Load Dataset
      Ã¢â€â€š
      Ã¢â€“Â¼
Feature Selection
      Ã¢â€â€š
      Ã¢â€“Â¼
Train Random Forest
      Ã¢â€â€š
      Ã¢â€“Â¼
Save Model
      Ã¢â€â€š
      Ã¢â€“Â¼
Load Model
      Ã¢â€â€š
      Ã¢â€“Â¼
Prediction API
```

---

# Ã°Å¸Â§Âª Running Tests

Install development dependencies

```bash
pip install -r requirements-dev.txt
```

Run tests

```bash
python -m pytest -q
```

---

# Ã°Å¸â€œÅ  Current Capabilities

Ã¢Å“â€ Automatic model training if no saved model exists

Ã¢Å“â€ Predicts a binary SLA breach-risk label

Ã¢Å“â€ Suggests target routing team

Ã¢Å“â€ Uses Random Forest classifier

Ã¢Å“â€ RESTful API interface

Ã¢Å“â€ Lightweight backend implementation

## Data and Model Limitations

The bundled dataset contains only three sample tickets. It is enough to exercise
the training and prediction flow, but not to measure model quality or claim
production accuracy. The pipeline uses `priority` and `created_hours` as
prediction-time inputs; `ticket_id`, `assigned_team`, and `sla_breach` are not
features. See [the ML data and leakage audit](docs/ml_data_audit.md) for the
target definition, validation rules, artifact design, and evaluation limits.

---

# Ã°Å¸Å¡â‚¬ Future Improvements

- Representative, timestamped ticket data before evaluating or expanding ML
- Live JIRA provider only with approved credentials and network integration
- Browser-level interaction tests for the dependency-free frontend
- Production shared rate-limit storage for multi-instance deployments

---

# Ã°Å¸â€œÅ“ License

This project is licensed under the **MIT License**.

---

<div align="center">

## Ã°Å¸â€˜Â¨Ã¢â‚¬ÂÃ°Å¸â€™Â» Developer

### **Basani Ganesh**

Ã°Å¸Å½â€œ B.Tech Ã¢â‚¬â€œ Computer Science & Engineering

Ã°Å¸â€™Â» Passionate about Full Stack Development, AI & Machine Learning

Ã°Å¸â€â€” GitHub

https://github.com/Ganeshbasani


</div>


