# Custom Docker Image Request for DoD Environment

## Problem Statement

The Sprint Metrics Dashboard CI/CD pipeline requires DoD root CA certificates to validate SSL connections to `git.example.com`. The current workaround uses CI/CD variables to install certificates on each pipeline run, which is complex and adds overhead.

## Proposed Solution

Create a custom Docker image based on `python:3.12-slim` with DoD CA certificates pre-installed.

## Benefits

1. **Simplicity** - Certificates work automatically, no CI/CD variable configuration
2. **Performance** - Faster pipeline runs (no certificate installation per job)
3. **Reliability** - Consistent environment across all pipeline executions
4. **Maintainability** - Single source of truth, easy to version and update

## Technical Requirements

### Base Image
```
python:3.12-slim
```

### Required Packages
- git
- ca-certificates (Debian package)

### Required Certificates
DoD Root CA certificate bundle containing ~49 certificates from the DoD PKI chain.

**Source**: `/usr/local/share/ca-certificates/dod.crt` (available on DoD workstations)

**Size**: ~97KB

**Format**: PEM-encoded certificate bundle

### Dockerfile

```dockerfile
FROM python:3.12-slim

# Metadata
LABEL maintainer="Sprint Metrics Dashboard Team"
LABEL description="Python 3.12 with DoD CA certificates for GitLab CI/CD"
LABEL version="1.0"

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy DoD certificate bundle
# Note: This file should be provided by the build context
COPY dod.crt /usr/local/share/ca-certificates/dod_bundle.crt

# Update CA certificate trust store
RUN update-ca-certificates

# Set environment variables for SSL verification
ENV GITLAB_SSL_VERIFY=true \
    GIT_SSL_NO_VERIFY=0 \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

# Default working directory
WORKDIR /builds

# Verify certificates are installed
RUN python3 -c "import ssl; print('SSL context created successfully')" && \
    git config --global http.sslVerify true

CMD ["/bin/bash"]
```

### Build Instructions

```bash
# Place dod.crt in the build context
cp /usr/local/share/ca-certificates/dod.crt .

# Build the image
docker build -t <registry>/python-dod-certs:3.12 -t <registry>/python-dod-certs:latest .

# Test the image locally
docker run --rm <registry>/python-dod-certs:3.12 python3 -c "import requests; requests.get('https://git.example.com')"

# Push to registry
docker push <registry>/python-dod-certs:3.12
docker push <registry>/python-dod-certs:latest
```

### Image Naming Convention

**Recommended**: `<registry>/python-dod-certs:3.12`

Where:
- `<registry>` = Your organization's container registry
- `python-dod-certs` = Descriptive image name
- `3.12` = Python version tag (allows for versioning)
- `latest` = Additional tag for convenience

### Size Estimate

- Base `python:3.12-slim`: ~130 MB
- Additional packages: ~10 MB
- DoD certificates: ~0.1 MB
- **Total**: ~140 MB

## Usage in GitLab CI/CD

Once the image is available, the `.gitlab-ci.yml` can be simplified to:

```yaml
.python_setup: &python_setup
  image: <registry>/python-dod-certs:3.12
  before_script:
    - pip install --quiet -r scripts/requirements.txt
```

**Removed complexity**:
- No `DOD_CA_CERT` CI/CD variable needed
- No certificate installation logic in `before_script`
- No conditional SSL verification setup
- Approximately 30 lines of shell script eliminated

## Maintenance

### Updating Certificates

When DoD root certificates are updated:

1. Obtain new `dod.crt` file
2. Rebuild image with new certificate bundle
3. Push new version (e.g., `3.12-v2` or dated tag `3.12-20260211`)
4. Update `.gitlab-ci.yml` to reference new image tag
5. Run test pipeline to verify

### Python Version Updates

To upgrade Python version (e.g., 3.13):

1. Update Dockerfile `FROM python:3.13-slim`
2. Build with new tag: `python-dod-certs:3.13`
3. Test thoroughly
4. Update projects to use new image

## Security Considerations

1. **Certificate Source** - Ensure `dod.crt` is obtained from trusted DoD PKI sources
2. **Registry Access** - Limit image pull access to authorized CI/CD runners
3. **Image Scanning** - Scan for vulnerabilities before deployment
4. **Signing** - Consider signing images for supply chain security
5. **Version Control** - Track Dockerfile changes in git

## Testing Checklist

Before deploying to production pipelines, verify:

- [ ] SSL connections to `git.example.com` succeed
- [ ] `pip install` works without SSL errors
- [ ] Python `requests` library validates certificates correctly
- [ ] Git operations with SSL verification enabled work
- [ ] All 49 DoD certificates are present in trust store
- [ ] Image size is reasonable (~140 MB)
- [ ] Build is reproducible

## Rollback Plan

If issues arise with the custom image:

1. Update `.gitlab-ci.yml` to use `python:3.12-slim` (official image)
2. Re-enable `DOD_CA_CERT` CI/CD variable approach
3. Restore previous `before_script` certificate installation logic

## Alternative Approaches

If a custom image is not feasible:

**Option A: Shared Runner with Pre-installed Certificates**
- Configure GitLab Runners with DoD certificates in system trust store
- Use standard Python images, certificates available automatically

**Option B: Continue with CI/CD Variable Approach**
- Current implementation (functional but complex)
- See `docs/SSL_CERTIFICATE_SETUP.md` for details

## References

- Base Image: https://hub.docker.com/_/python
- Dockerfile Best Practices: https://docs.docker.com/develop/develop-images/dockerfile_best-practices/
- GitLab CI/CD Docker Images: https://docs.gitlab.com/ee/ci/docker/using_docker_images.html
- DoD PKI: https://public.cyber.mil/pki-pke/

## Contact

For questions or assistance with this request, contact the Sprint Metrics Dashboard team.

**Project**: tinkers/sprint-metrics-dashboard
**GitLab Instance**: https://git.example.com
