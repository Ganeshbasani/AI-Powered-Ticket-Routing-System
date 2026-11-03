# Deployment Readiness

The container is built in two stages: Node builds the dependency-free frontend,
then a Python 3.12 slim runtime installs pinned requirements and runs as a
non-root `app` user. It exposes port 5000 and checks `/api/v1/health`.

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
