<div align="center">

# 🚀 Live Demo — Recruiter Access

### 🌐 Try the Deployed Application

**🔗 Live Demo:** https://ai-powered-ticket-routing-system.onrender.com/

> ### 🔐 Demo Credentials
> **Demo ID:** `Demo@gmail.com`  
> **Password:** `Demo@1234`
>
> Use the dedicated demo account to explore the deployed ticket-management, automatic prediction, prediction-history, and analytics workflows.

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
docker run --rm -p 10000:10000 --env-file .env sla-ticket-routing
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

# 📌 Table of Contents

- Live Demo
- UI Showcase
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

# 📖 Overview

Managing support tickets efficiently is critical for reducing response times and maintaining Service Level Agreements (SLAs).

This project demonstrates how machine learning can assist support teams by predicting whether a ticket is likely to breach its SLA and providing a transparent routing recommendation.

The project is implemented as a backend-focused prototype with a REST API built using Flask.

---

# ✨ Features

✅ Predict SLA Breach Risk

✅ Intelligent Ticket Routing

✅ REST API using Flask

✅ Random Forest Machine Learning Model

✅ Automatic Model Training

✅ Health Check Endpoint

✅ Clean Project Structure

✅ Automated Unit Testing

---

# 🛠️ Tech Stack

| Category | Technology |
|-----------|------------|
| Language | Python |
| Backend | Flask |
| Machine Learning | Scikit-Learn |
| Data Processing | Pandas |
| Model Storage | Joblib |
| Testing | Pytest |

---

# 🧠 Project Architecture

```text
                Ticket Data
                     │
                     ▼
              Data Preprocessing
                     │
                     ▼
          Random Forest Training
                     │
             Saved ML Model
                     │
                     ▼
             Flask REST API
                     │
                     ▼
        SLA Prediction + Team Routing
```

---

# 📂 Project Structure

```text
AI-Powered-Ticket-Routing-System
│
Ã¢”Å“├├ api/
│
Ã¢”Å“├├ data/
│   └├├ tickets.csv
│
Ã¢”Å“├├ docs/
│
Ã¢”Å“├├ ml_model/
│
Ã¢”Å“├├ src/
│
Ã¢”Å“├├ tests/
│
Ã¢”Å“├├ app.py
│
Ã¢”Å“├├ requirements.txt
│
Ã¢”Å“├├ requirements-dev.txt
│
└├├ README.md
```

---

# ⚙️ Installation

## Clone Repository

```bash
git clone https://github.com/Ganeshbasani/AI-Powered-Ticket-Routing-System.git

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

# ▶️ Run the Application

```bash
python app.py
```

Server starts at

```
http://127.0.0.1:5000
```

---

# Ã°Å¸Å’ REST API

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

# 🤖 Machine Learning Workflow

```text
Load Dataset
      │
      ▼
Feature Selection
      │
      ▼
Train Random Forest
      │
      ▼
Save Model
      │
      ▼
Load Model
      │
      ▼
Prediction API
```

---

# 🧪 Running Tests

Install development dependencies

```bash
pip install -r requirements-dev.txt
```

Run tests

```bash
python -m pytest -q
```

---

# 📊 Current Capabilities

Ã¢Å“” Automatic model training if no saved model exists

Ã¢Å“” Predicts a binary SLA breach-risk label

Ã¢Å“” Suggests target routing team

Ã¢Å“” Uses Random Forest classifier

Ã¢Å“” RESTful API interface

Ã¢Å“” Lightweight backend implementation

## Data and Model Limitations

The bundled dataset contains only three sample tickets. It is enough to exercise
the training and prediction flow, but not to measure model quality or claim
production accuracy. The pipeline uses `priority` and `created_hours` as
prediction-time inputs; `ticket_id`, `assigned_team`, and `sla_breach` are not
features. See [the ML data and leakage audit](docs/ml_data_audit.md) for the
target definition, validation rules, artifact design, and evaluation limits.

---

# 🚀 Future Improvements

- Representative, timestamped ticket data before evaluating or expanding ML
- Live JIRA provider only with approved credentials and network integration
- Browser-level interaction tests for the dependency-free frontend
- Production shared rate-limit storage for multi-instance deployments

---

# 📜 License

This project is licensed under the **MIT License**.

---

<div align="center">

## 👨‍💻 Developer

### **Basani Ganesh**

🎓 B.Tech Ã¢â‚¬“ Computer Science & Engineering

💻 Passionate about Full Stack Development, AI & Machine Learning

🔗 GitHub

https://github.com/Ganeshbasani


</div>
