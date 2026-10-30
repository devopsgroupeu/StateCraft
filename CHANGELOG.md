# Changelog

All notable changes to this project will be documented in this file.

## [0.6.5](https://github.com/devopsgroupeu/StateCraft/compare/v0.6.4...v0.6.5) (2026-10-30)

### 🐛 Bug Fixes

* **chart:** let the NetworkPolicy reach the AWS APIs and resolve DNS over TCP (OP-261) ([#27](https://github.com/devopsgroupeu/StateCraft/issues/27)) ([c35b4e2](https://github.com/devopsgroupeu/StateCraft/commit/c35b4e25f0f2f568d445e9d5a6f56c9e20fe8727))

## [0.6.4](https://github.com/devopsgroupeu/StateCraft/compare/v0.6.3...v0.6.4) (2026-10-30)

### 🐛 Bug Fixes

* make API docs opt-in, validate X-Request-ID and stop mounting the SA token (OP-270) ([#26](https://github.com/devopsgroupeu/StateCraft/issues/26)) ([ce97b18](https://github.com/devopsgroupeu/StateCraft/commit/ce97b1810e8afdfac70943049225e0376c78539f))

## [0.6.3](https://github.com/devopsgroupeu/StateCraft/compare/v0.6.2...v0.6.3) (2026-10-29)

### 🐛 Bug Fixes

* **core:** refuse foreign buckets and tables, delete safely and keep secrets out of errors (OP-261) ([#24](https://github.com/devopsgroupeu/StateCraft/issues/24)) ([1ea56da](https://github.com/devopsgroupeu/StateCraft/commit/1ea56dacb7e6c228a43c31b4c5314365ca95d2ef))

## [0.6.2](https://github.com/devopsgroupeu/StateCraft/compare/v0.6.1...v0.6.2) (2026-10-29)

### 🐛 Bug Fixes

* **core:** refuse requests without customer credentials instead of using our own (OP-258) ([#22](https://github.com/devopsgroupeu/StateCraft/issues/22)) ([3438f4c](https://github.com/devopsgroupeu/StateCraft/commit/3438f4cc6567bad6bacb638210820d959c1b310b))

## [0.6.1](https://github.com/devopsgroupeu/StateCraft/compare/v0.6.0...v0.6.1) (2026-10-29)

### 🐛 Bug Fixes

* **auth:** refuse to start or serve without a service token (OP-260) ([#21](https://github.com/devopsgroupeu/StateCraft/issues/21)) ([c7425d7](https://github.com/devopsgroupeu/StateCraft/commit/c7425d7778615da293e24fdac8834ca0b0c49b8b))

## [0.6.0](https://github.com/devopsgroupeu/StateCraft/compare/v0.5.2...v0.6.0) (2026-10-29)

### 🚀 Features

* **metrics:** expose red metrics on a dedicated port (OP-176) ([#20](https://github.com/devopsgroupeu/StateCraft/issues/20)) ([9543bd5](https://github.com/devopsgroupeu/StateCraft/commit/9543bd5fda9ddd6255ec45c2f6fbd680e837ab70))

### 🐛 Bug Fixes

* **api:** run blocking aws calls off the event loop so health checks keep answering (OP-264) ([#23](https://github.com/devopsgroupeu/StateCraft/issues/23)) ([66de0bc](https://github.com/devopsgroupeu/StateCraft/commit/66de0bcbd1d9c20bc2471ad2e11371d726a29133))

## [0.6.0](https://github.com/devopsgroupeu/StateCraft/compare/v0.5.2...v0.6.0) (2026-10-28)

### 🚀 Features

* **metrics:** expose red metrics on a dedicated port (OP-176) ([#20](https://github.com/devopsgroupeu/StateCraft/issues/20)) ([9543bd5](https://github.com/devopsgroupeu/StateCraft/commit/9543bd5fda9ddd6255ec45c2f6fbd680e837ab70))

## [0.5.2](https://github.com/devopsgroupeu/StateCraft/compare/v0.5.1...v0.5.2) (2026-08-11)

### 🐛 Bug Fixes

* **packaging:** run StateCraft as a real package and report the running version ([#19](https://github.com/devopsgroupeu/StateCraft/issues/19)) ([074fe76](https://github.com/devopsgroupeu/StateCraft/commit/074fe76a4ac40e3dfc5df951afa72decfa58b618))

## [0.5.1](https://github.com/devopsgroupeu/StateCraft/compare/v0.5.0...v0.5.1) (2026-07-11)

### 🐛 Bug Fixes

* **statecraft:** harden state-bucket creation (us-east-1, retry-safety, error surfacing) ([#17](https://github.com/devopsgroupeu/StateCraft/issues/17)) ([02c2980](https://github.com/devopsgroupeu/StateCraft/commit/02c29804ecb99fe559eff3b495e1b103e7a24244))

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
