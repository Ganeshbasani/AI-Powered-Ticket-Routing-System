# AWS Deployment — ECR + App Runner

This is the Stage 3 cloud path for the fresher version of the project.

## Architecture

```text
GitHub push to main
        |
        v
GitHub Actions (OIDC)
        |
        v
Amazon ECR
        |
        v
AWS App Runner
        |
        v
Flask + frontend container
```

The workflow uses GitHub OIDC to obtain short-lived AWS credentials rather than storing long-lived access keys in the repository. AWS recommends OIDC for GitHub Actions authentication. See the official guidance linked from the project README.

## One-time AWS setup

### 1. Create an ECR repository

Create a private ECR repository named:

```text
ai-powered-ticket-routing
```

The repository must exist before the GitHub workflow pushes its first image.

### 2. Create a GitHub OIDC identity provider

In IAM, add the GitHub OIDC provider:

```text
https://token.actions.githubusercontent.com
```

Audience:

```text
sts.amazonaws.com
```

### 3. Create an IAM role for GitHub Actions

Create a role trusted by your GitHub repository. Restrict the trust policy to your exact repository and `main` branch.

Replace the placeholders in the example below:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::<AWS_ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:<GITHUB_OWNER>/<GITHUB_REPOSITORY>:ref:refs/heads/main"
        }
      }
    }
  ]
}
```

Attach a least-privilege ECR push policy to the role. The required ECR actions are the repository inspection/authentication actions plus layer upload and image push actions.

### 4. Add the GitHub secret

Repository → Settings → Secrets and variables → Actions → New repository secret:

```text
AWS_GITHUB_ACTIONS_ROLE_ARN
```

Value:

```text
arn:aws:iam::<AWS_ACCOUNT_ID>:role/<ROLE_NAME>
```

Do not commit AWS keys, passwords, or the role ARN to source code.

### 5. Configure App Runner

Create an App Runner service from the private ECR image:

```text
ECR repository: ai-powered-ticket-routing
Image tag: latest
Port: 10000
Health check path: /api/v1/health
```

Use automatic deployment for the ECR image. App Runner can run a ready-to-deploy container image stored in Amazon ECR.

### 6. Configure application secrets

Set these as App Runner environment variables/secrets:

```text
APP_ENV=production
FLASK_DEBUG=False
PORT=10000
FLASK_PORT=10000
ALLOW_MODEL_TRAINING=False
AUTH_SECRET_KEY=<strong-random-secret>
BOOTSTRAP_ADMIN_EMAIL=<admin-email>
BOOTSTRAP_ADMIN_PASSWORD=<strong-password>
```

The production container is deliberately configured not to train a model at runtime. The model artifact is validated during image build and loaded during application startup.

## Database note

Stage 3 intentionally keeps SQLite so the project remains simple for a fresher. SQLite is suitable for local/demo use, but a multi-instance cloud deployment should move ticket state to a managed database such as Amazon RDS for PostgreSQL before being presented as a production deployment.

## Deploy flow

After setup:

```bash
git add .
git commit -m "chore: add AWS CI/CD deployment"
git push origin main
```

GitHub Actions will:

1. Authenticate to AWS with OIDC.
2. Log in to ECR.
3. Build the existing Docker image.
4. Push both the commit SHA tag and `latest`.
5. Let App Runner roll the `latest` image through its configured automatic deployment.

## Verification

After App Runner finishes deployment:

```text
GET https://<your-app-runner-url>/api/v1/health
GET https://<your-app-runner-url>/api/v1/ready
```

Expected responses:

```json
{"status":"ok"}
```

and:

```json
{"status":"ready"}
```

The deployed application still uses the existing `/` frontend entry point.
