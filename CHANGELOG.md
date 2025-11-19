# Changelog

## [0.3.0] - 2025-11-19

### Added

- Helm chart for Kubernetes deployment with production-ready configuration
- Support for Kubernetes deployment with configurable replicas, resources, and autoscaling
- Service, Ingress, and ServiceAccount Kubernetes resources in Helm templates
- Comprehensive Helm values with sensible defaults for cloud-native deployments

### Fixed

- Log file path changed to `/tmp/statecraft.log` for compatibility with Kubernetes read-only filesystems
- Application now works correctly in containerized environments with restricted filesystem access

## [0.2.0] - 2025-11-18

### Added

- REST API server mode with FastAPI-based endpoints
- Health check endpoint (`/health`) for monitoring
- Resource creation endpoint (`/resources/create`)
- Resource deletion endpoint (`/resources/delete`)
- Dual-mode entrypoint supporting both CLI and server modes
- Comprehensive API documentation with multiple authentication patterns
- Security warnings and best practices for credential handling
- Docker port exposure (8000) for API server mode

### Changed

- Updated Dockerfile to support both CLI and API server modes
- Enhanced `docker-compose.yml` with separate services for CLI and server modes
- Restructured application entry point to support mode selection

### Security

- Added SSL certificate patterns to `.gitignore`
- Included comprehensive security warnings for production deployments
- Documented IAM role usage as preferred authentication method

## [0.1.0] - 2025-08-01

### Added

- Initial public release
- CLI for provisioning S3 and DynamoDB-based backends
- Support for Terraform state locking (S3/DynamoDB)
- Dockerfile for containerized usage
- GitHub Actions CI pipeline
- Project documentation and usage examples
- Instructions for docker
- docker-compose.yml file
