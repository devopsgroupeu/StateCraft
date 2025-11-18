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
python3 src/main.py \
    create \ # or delete
    --region eu-west-1 \
    --bucket-name my-terraform-bucket \
    --locking-mechanism s3
```

#### DynamoDB locking mechanisim

```sh
python3 src/main.py \
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
- Use **IAM roles** (e.g., ECS Task Role, EC2 Instance Profile) when running in AWS
- Never log or persist credentials
- Deploy behind a reverse proxy with TLS termination

```sh
docker run -d -p 8000:8000 \
    ghcr.io/devopsgroupeu/statecraft:latest server
```

Access API documentation at `http://localhost:8000/docs`

**Option 1: Per-request credentials (multi-account support):**
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

**Option 2: Environment variables (single account, more secure):**
```sh
docker run -d -p 8000:8000 \
    -e AWS_ACCESS_KEY_ID=ASIAIOSFODNN7EXAMPLE \
    -e AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY \
    ghcr.io/devopsgroupeu/statecraft:latest server

curl -X POST http://localhost:8000/resources/create \
    -H "Content-Type: application/json" \
    -d '{
        "region": "eu-west-1",
        "bucket_name": "my-terraform-bucket",
        "table_name": "my-terraform-dynamodb",
        "locking_mechanism": "dynamodb"
    }'
```

**Option 3: AWS IAM Roles (most secure for production):**
```sh
# When running on AWS (ECS, EC2, Lambda), use IAM roles - no credentials needed
docker run -d -p 8000:8000 ghcr.io/devopsgroupeu/statecraft:latest server

# Requests don't need credentials - automatically uses task/instance role
curl -X POST http://localhost:8000/resources/create \
    -H "Content-Type: application/json" \
    -d '{
        "region": "eu-west-1",
        "bucket_name": "my-terraform-bucket",
        "table_name": "my-terraform-dynamodb",
        "locking_mechanism": "dynamodb"
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
   - ✅ Use HTTPS with valid TLS certificates
   - ✅ Deploy behind reverse proxy with rate limiting
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
