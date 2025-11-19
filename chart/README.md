# StateCraft Helm Chart

This Helm chart deploys StateCraft, an AWS Terraform State Backend Infrastructure Manager, to a Kubernetes cluster.

## Overview

StateCraft is a FastAPI microservice that manages AWS infrastructure resources for Terraform state backends. It automates the creation and deletion of:
- **Amazon S3 buckets** for Terraform state storage (with versioning and encryption)
- **Amazon DynamoDB tables** for distributed state locking

## Prerequisites

- Kubernetes 1.19+
- Helm 3.0+
- AWS credentials with appropriate permissions (S3, DynamoDB)
- PV provisioner support in the underlying infrastructure (optional)

## Installing the Chart

### Quick Install

```bash
helm install statecraft ./chart
```

### Install with Custom Values

```bash
helm install statecraft ./chart \
  --set aws.credentials.accessKeyId="YOUR_ACCESS_KEY" \
  --set aws.credentials.secretAccessKey="YOUR_SECRET_KEY" \
  --set aws.credentials.defaultRegion="us-east-1"
```

### Install with Values File

Create a `custom-values.yaml` file:

```yaml
aws:
  credentials:
    accessKeyId: "YOUR_ACCESS_KEY"
    secretAccessKey: "YOUR_SECRET_KEY"
    defaultRegion: "us-east-1"

ingress:
  enabled: true
  className: "nginx"
  hosts:
    - host: statecraft.example.com
      paths:
        - path: /
          pathType: Prefix
```

Install with the custom values:

```bash
helm install statecraft ./chart -f custom-values.yaml
```

## Uninstalling the Chart

```bash
helm uninstall statecraft
```

## Configuration

The following table lists the configurable parameters of the StateCraft chart and their default values.

### General Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `replicaCount` | Number of StateCraft replicas | `2` |
| `image.repository` | StateCraft image repository | `ghcr.io/devopsgroupeu/statecraft` |
| `image.pullPolicy` | Image pull policy | `IfNotPresent` |
| `image.tag` | Image tag (overrides appVersion) | `""` |
| `imagePullSecrets` | Image pull secrets | `[{name: "ghcr-secret"}]` |
| `nameOverride` | Override chart name | `""` |
| `fullnameOverride` | Override full chart name | `""` |

### Service Account

| Parameter | Description | Default |
|-----------|-------------|---------|
| `serviceAccount.create` | Create service account | `true` |
| `serviceAccount.annotations` | Service account annotations | `{}` |
| `serviceAccount.name` | Service account name | `""` |

### Security Context

| Parameter | Description | Default |
|-----------|-------------|---------|
| `podSecurityContext.fsGroup` | Pod filesystem group ID | `1000` |
| `podSecurityContext.runAsNonRoot` | Run as non-root user | `true` |
| `podSecurityContext.runAsUser` | User ID to run container | `1000` |
| `securityContext.allowPrivilegeEscalation` | Allow privilege escalation | `false` |
| `securityContext.capabilities.drop` | Linux capabilities to drop | `["ALL"]` |
| `securityContext.readOnlyRootFilesystem` | Read-only root filesystem | `false` |

### Service

| Parameter | Description | Default |
|-----------|-------------|---------|
| `service.type` | Kubernetes service type | `ClusterIP` |
| `service.port` | Service port | `80` |
| `service.targetPort` | Container target port | `8000` |

### Ingress

| Parameter | Description | Default |
|-----------|-------------|---------|
| `ingress.enabled` | Enable ingress | `false` |
| `ingress.className` | Ingress class name | `""` |
| `ingress.annotations` | Ingress annotations | `{}` |
| `ingress.hosts` | Ingress hosts configuration | `[{host: "statecraft.local", paths: [{path: "/", pathType: "Prefix"}]}]` |
| `ingress.tls` | Ingress TLS configuration | `[]` |

### Resources

| Parameter | Description | Default |
|-----------|-------------|---------|
| `resources.limits.cpu` | CPU limit | `200m` |
| `resources.limits.memory` | Memory limit | `256Mi` |
| `resources.requests.cpu` | CPU request | `100m` |
| `resources.requests.memory` | Memory request | `128Mi` |

### Autoscaling

| Parameter | Description | Default |
|-----------|-------------|---------|
| `autoscaling.enabled` | Enable HPA | `false` |
| `autoscaling.minReplicas` | Minimum replicas | `2` |
| `autoscaling.maxReplicas` | Maximum replicas | `10` |
| `autoscaling.targetCPUUtilizationPercentage` | Target CPU utilization | `80` |
| `autoscaling.targetMemoryUtilizationPercentage` | Target memory utilization | `80` |

### AWS Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `aws.existingSecret` | Use existing secret for AWS credentials | `""` |
| `aws.secretKeys.accessKeyId` | Secret key for AWS access key ID | `AWS_ACCESS_KEY_ID` |
| `aws.secretKeys.secretAccessKey` | Secret key for AWS secret access key | `AWS_SECRET_ACCESS_KEY` |
| `aws.secretKeys.defaultRegion` | Secret key for AWS default region | `AWS_DEFAULT_REGION` |
| `aws.credentials.accessKeyId` | AWS access key ID (dev only) | `""` |
| `aws.credentials.secretAccessKey` | AWS secret access key (dev only) | `""` |
| `aws.credentials.defaultRegion` | AWS default region | `"us-east-1"` |
| `aws.useIRSA` | Use IAM Roles for Service Accounts (EKS) | `false` |
| `aws.irsaRoleArn` | IAM role ARN for IRSA | `""` |

### Application Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `app.env.LOG_LEVEL` | Application log level | `"INFO"` |

### Health Checks

| Parameter | Description | Default |
|-----------|-------------|---------|
| `healthCheck.enabled` | Enable health checks | `true` |
| `healthCheck.livenessProbe.httpGet.path` | Liveness probe path | `/health` |
| `healthCheck.livenessProbe.initialDelaySeconds` | Initial delay for liveness probe | `30` |
| `healthCheck.readinessProbe.httpGet.path` | Readiness probe path | `/health` |
| `healthCheck.readinessProbe.initialDelaySeconds` | Initial delay for readiness probe | `10` |

### Network Policy

| Parameter | Description | Default |
|-----------|-------------|---------|
| `networkPolicy.enabled` | Enable network policies | `false` |
| `networkPolicy.ingress` | Ingress network policy rules | See values.yaml |
| `networkPolicy.egress` | Egress network policy rules | See values.yaml |

## AWS Credentials Configuration

### Option 1: Use Existing Secret (Recommended for Production)

Create a secret with your AWS credentials:

```bash
kubectl create secret generic statecraft-aws-creds \
  --from-literal=AWS_ACCESS_KEY_ID=your-access-key \
  --from-literal=AWS_SECRET_ACCESS_KEY=your-secret-key \
  --from-literal=AWS_DEFAULT_REGION=us-east-1
```

Configure Helm values:

```yaml
aws:
  existingSecret: "statecraft-aws-creds"
```

### Option 2: Use Helm Values (Development Only)

```yaml
aws:
  credentials:
    accessKeyId: "YOUR_ACCESS_KEY"
    secretAccessKey: "YOUR_SECRET_KEY"
    defaultRegion: "us-east-1"
```

**⚠️ Warning:** This method stores credentials in plain text. Only use for development.

### Option 3: Use IAM Roles for Service Accounts (IRSA) - Recommended for EKS

For AWS EKS clusters, use IRSA for secure credential management:

1. Create an IAM role with the required permissions
2. Associate it with the service account

```yaml
aws:
  useIRSA: true
  irsaRoleArn: "arn:aws:iam::ACCOUNT_ID:role/StateCraftRole"

serviceAccount:
  create: true
  annotations:
    eks.amazonaws.com/role-arn: "arn:aws:iam::ACCOUNT_ID:role/StateCraftRole"
```

## Required AWS IAM Permissions

StateCraft requires the following AWS IAM permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:CreateBucket",
        "s3:DeleteBucket",
        "s3:PutBucketVersioning",
        "s3:PutBucketEncryption",
        "s3:PutPublicAccessBlock",
        "s3:DeleteObject",
        "s3:ListBucketVersions",
        "s3:HeadBucket"
      ],
      "Resource": "arn:aws:s3:::*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:CreateTable",
        "dynamodb:DeleteTable",
        "dynamodb:DescribeTable"
      ],
      "Resource": "arn:aws:dynamodb:*:*:table/*"
    }
  ]
}
```

## Accessing StateCraft API

### Using Port-Forward (Development)

```bash
kubectl port-forward svc/statecraft 8000:80
```

Access the API at `http://localhost:8000`

### Using Ingress (Production)

Enable ingress and configure your domain:

```yaml
ingress:
  enabled: true
  className: "nginx"
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
  hosts:
    - host: statecraft.example.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: statecraft-tls
      hosts:
        - statecraft.example.com
```

## API Endpoints

- `GET /` - Basic health check
- `GET /health` - Detailed health information
- `POST /resources/create` - Create S3 bucket and DynamoDB table
- `POST /resources/delete` - Delete S3 bucket and DynamoDB table
- `GET /docs` - Interactive API documentation (Swagger UI)

## Examples

### Create Terraform State Backend

```bash
curl -X POST http://statecraft.example.com/resources/create \
  -H "Content-Type: application/json" \
  -d '{
    "region": "us-east-1",
    "bucket_name": "my-terraform-state",
    "table_name": "my-terraform-locks",
    "locking_mechanism": "dynamodb"
  }'
```

### Delete Terraform State Backend

```bash
curl -X POST http://statecraft.example.com/resources/delete \
  -H "Content-Type: application/json" \
  -d '{
    "region": "us-east-1",
    "bucket_name": "my-terraform-state",
    "table_name": "my-terraform-locks"
  }'
```

## Troubleshooting

### Check Pod Status

```bash
kubectl get pods -l app.kubernetes.io/name=statecraft
```

### View Logs

```bash
kubectl logs -l app.kubernetes.io/name=statecraft -f
```

### Check Service Endpoints

```bash
kubectl get endpoints statecraft
```

### Test Health Endpoint

```bash
kubectl run curl --image=curlimages/curl -i --rm --restart=Never -- \
  curl http://statecraft/health
```

## Upgrading

### Upgrade to Latest Version

```bash
helm upgrade statecraft ./chart
```

### Upgrade with New Values

```bash
helm upgrade statecraft ./chart -f custom-values.yaml
```

## Support

For issues and feature requests, please visit:
- GitHub: https://github.com/devopsgroupeu/statecraft
- Issues: https://github.com/devopsgroupeu/statecraft/issues

## License

MIT License - see LICENSE file for details
