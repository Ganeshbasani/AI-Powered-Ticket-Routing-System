# Deployment Readiness

The container is built in two stages: Node builds the dependency-free frontend,
then a Python 3.12 slim runtime installs pinned requirements and runs as a
non-root `app` user. Gunicorn binds to `0.0.0.0:$PORT` and the health check uses
`/api/v1/health`. Local `python app.py` and `python wsgi.py` use `FLASK_HOST`
and `FLASK_PORT`; `PORT` is used when `FLASK_PORT` is not set. Development mode
serves `frontend/src` directly when no build output exists.

## Persistent SQLite on Render

The Blueprint mounts `/var/data` and sets `DATABASE_PATH=/var/data/platform.db`.
This path remains outside the repository tree so a deploy cannot accidentally
copy a local database into the image. The database object runs the existing
non-destructive migrations on startup. Existing local records stay in the local
database; move them to the mounted volume deliberately before using a new hosted
database. The first Render deployment does not migrate local files automatically.

Render only supports persistent disks on paid web services. The Blueprint uses
the `starter` plan for that reason. A disk-backed service runs as one instance,
and deploys have a short interruption. The local Docker build still uses an
ephemeral `/var/data` unless a volume is mounted by the operator.

CI compiles Python, runs backend tests, performs frontend static-contract and
build checks, and builds the Docker image. It does not deploy candidate models
or containers.

## AWS Boundary

The repository contains no AWS credentials, ECR repository, ECS service, IAM
role, subnet, or secret identifiers. A future deployment must supply those as
environment-specific infrastructure configuration. Use a least-privilege task
role, inject `AUTH_SECRET_KEY` through a secrets manager, identify the baseline
artifact by SHA-256, and retain it for rollback. Do not promote synthetic
candidate artifacts automatically.

## Rollback

Deployments should pin an immutable container image and the baseline artifact
hash. Roll back by redeploying the prior image and preserving the existing
`ml_model/sla_model.joblib`; candidate artifacts under `ml_model/candidates`
are not runtime inputs.
