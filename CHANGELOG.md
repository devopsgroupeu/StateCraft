# Changelog

All notable changes to this project will be documented in this file.

## [0.5.0](https://github.com/devopsgroupeu/StateCraft/compare/v0.4.4...v0.5.0) (2026-07-07)

### 🚀 Features

* **logging:** unified JSON logs with cross-service request-id correlation ([#15](https://github.com/devopsgroupeu/StateCraft/issues/15)) ([6692046](https://github.com/devopsgroupeu/StateCraft/commit/66920469ae4d115656119717453ebd161a657b03))

## [0.4.4](https://github.com/devopsgroupeu/StateCraft/compare/v0.4.3...v0.4.4) (2026-07-07)

### 🏗️ Build System

* adopt semantic-release pipeline and enable CI (unified versioning) ([#14](https://github.com/devopsgroupeu/StateCraft/issues/14)) ([b5ad3f5](https://github.com/devopsgroupeu/StateCraft/commit/b5ad3f5da9673e9b3997e617e32ff29729a98859))

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
