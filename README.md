# StateCraft

[![LinkedIn](https://img.shields.io/badge/linkedin-%230077B5.svg?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/company/devopsgroup8/)

![GitHub License](https://img.shields.io/github/license/devopsgroupeu/StateCraft)
![GitHub Forks](https://img.shields.io/github/forks/devopsgroupeu/StateCraft)
![GitHub Stars](https://img.shields.io/github/stars/devopsgroupeu/StateCraft)
![GitHub Watchers](https://img.shields.io/github/watchers/devopsgroupeu/StateCraft)
![GitHub Issues](https://img.shields.io/github/issues/devopsgroupeu/StateCraft)
![GitHub Last Commit](https://img.shields.io/github/last-commit/devopsgroupeu/StateCraft)
![Python Versions](https://img.shields.io/pypi/pyversions/statecraft)

Manage AWS resources (S3 Bucket and optional DynamoDB Table) for Terraform backend state.

Available as both CLI tool and REST API server.

## Diagram

![StateCraft diagram](./docs/img/statecraft.svg "StateCraft Diagram")

## 📝 Prerequisites

### 🔐 AWS Credentials

Don't forget to configure credentials to your AWS account. Learn more [here](https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-configure.html).

## ⚙️ Usage

### Local

#### S3 locking mechanisim

> For **Terraform version 1.11.0 or greater**.

```sh
python3 -m statecraft.main \
    create \ # or delete
    --region eu-west-1 \
    --bucket-name my-terraform-bucket \
    --locking-mechanism s3
```

#### DynamoDB locking mechanisim

```sh
python3 -m statecraft.main \
    create \ # or delete
    --region eu-west-1 \
    --bucket-name my-terraform-bucket \
    --table_name my-terraform-locking \
    --locking-mechanism dynamodb
```

### Docker

#### CLI Mode

```sh
docker run --rm \
    -e AWS_ACCESS_KEY_ID=ASIAIOSFODNN7EXAMPLE \
    -e AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY \
    -e AWS_DEFAULT_REGION=eu-west-1 \
    ghcr.io/devopsgroupeu/statecraft:latest create \
    --region eu-west-1 \
    --bucket-name my-terraform-bucket \
    --table-name my-terraform-dynamodb
```

#### API Server Mode

**⚠️ SECURITY WARNING**: When sending AWS credentials via API requests:
- **Always use HTTPS/TLS in production** to encrypt credentials in transit
- Consider using **AWS STS temporary credentials** instead of long-lived access keys
- Never log or persist credentials
- Deploy behind a reverse proxy with TLS termination

```sh
docker run -d -p 8000:8000 \
    -e SERVICE_TOKEN=change-me \
    ghcr.io/devopsgroupeu/statecraft:latest server
```

Access API documentation at `http://localhost:8000/docs`

**Authentication:** the server does not start without `SERVICE_TOKEN`, and every `/resources/*` request must send it in the `X-Service-Token` header. For local development only, `STATECRAFT_AUTH_DISABLED=true` lets the server run without a token; it has no effect once `SERVICE_TOKEN` is set.

Every `/resources/*` request must carry the target account's `aws_access_key_id` and `aws_secret_access_key`; a request without them is rejected with `400`. The API server never falls back to its own AWS identity (environment variables, shared config, or an attached IAM role), so no request can act as the server itself. The CLI does use the standard credential chain.

What the API refuses, so it never takes over or destroys something it did not create:
- **create** answers `409` for an existing bucket that StateCraft did not create for the same `environment`. Tags are merged into a bucket's existing tags, never replace them. `locking_mechanism` defaults to `s3` (native S3 locking); a DynamoDB lock table is created tagged and with deletion protection.
- **delete** needs `confirm` equal to `bucket_name`, a name matching `STATECRAFT_DELETE_ALLOWED_MARKERS`, and `ManagedBy=statecraft` on the bucket and on the lock table. Every check runs before anything is deleted; the bucket is deleted before the table; a table with deletion protection on answers `409` until it is unlocked deliberately. A bucket or table that is already gone counts as deleted.
- An unknown `region` answers `400`, and a `422` never echoes the request body.

```sh
curl -X POST http://localhost:8000/resources/create \
    -H "Content-Type: application/json" \
    -d '{
        "region": "eu-west-1",
        "bucket_name": "my-terraform-bucket",
        "table_name": "my-terraform-dynamodb",
        "locking_mechanism": "dynamodb",
        "aws_access_key_id": "ASIAIOSFODNN7EXAMPLE",
        "aws_secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    }'
```

### Production Deployment with HTTPS

Use the included `docker-compose.production.yml` for secure deployment:

```sh
# Generate self-signed certificates (for testing only)
mkdir -p ssl
openssl req -x509 -newkey rsa:4096 -nodes \
  -keyout ssl/key.pem -out ssl/cert.pem -days 365 \
  -subj "/CN=localhost"

# Start with HTTPS enabled
docker-compose -f docker-compose.production.yml up -d

# Access via HTTPS
curl -k https://localhost/health
```

For production, replace self-signed certificates with certificates from **Let's Encrypt** or your CA.

### Security Best Practices

1. **Production Deployment**:
   - Use HTTPS with valid TLS certificates
   - Deploy behind reverse proxy with rate limiting
   - Use AWS IAM roles instead of access keys when possible
   - Add authentication layer (OAuth2, API keys, mutual TLS)

2. **Credential Management**:
   - Prefer IAM roles > STS temporary credentials > long-lived access keys
   - Rotate access keys regularly
   - Use least-privilege IAM policies
   - Never commit credentials to git

3. **Monitoring**:
   - Enable AWS CloudTrail for API auditing
   - Monitor failed authentication attempts
   - Set up alerts for unusual resource creation patterns

## 📜 License

```
Copyright 2025 DevOpsGroup

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```

## 🤝 Contributing

We welcome contributions from everyone!
Please see our [Contributing Guidelines](CONTRIBUTING.md) to get started.

## 📜 Code of Conduct

Help us keep this community welcoming and respectful.
Read our [Code of Conduct](CODE_OF_CONDUCT.md) to understand the standards we uphold.

## 🗂️ Changelog

For a detailed history of changes, updates, and releases, please check out our [Changelog](CHANGELOG.md).
