# Getting Support for Runbox

Welcome to the Runbox support guide.

## Community Support & Discussions

- **GitHub Discussions:** For general questions, architecture discussions, integration advice, and community showcases, please open a thread in [GitHub Discussions](https://github.com/runbox/runbox/discussions).
- **GitHub Issues:** For confirmed bugs, unexpected runtime errors, or reproducible build failures, search existing issues first and submit a bug report with full reproduction steps, environment details (`uname -a`, `gcc --version`), and relevant logs.

## Documentation Index

Before filing an issue, please check the extensive documentation in `docs/`:
- [Architecture & System Design](file:///docs/architecture.md)
- [Security & Threat Model](file:///docs/threat_model.md)
- [Ubuntu 24.04 Deployment Guide](file:///docs/deployment/ubuntu_24_04.md)
- [REST API Specification](file:///docs/api.md)
- [Adversarial Verification Matrix](file:///docs/security/adversarial_test_matrix.md)
- [Performance & Benchmarking](file:///docs/benchmarking.md)

## Enterprise & Production Deployments

For high-security multi-tenant production deployments, review the [Native Linux Environment Verification](file:///docs/audit/native_linux_verification.md) and ensure that cgroups v2 hierarchy permissions and Landlock LSM support are properly initialized in systemd units.
