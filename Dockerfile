# Use a slim Python image for a smaller footprint. Pinned by digest (the
# multi-arch index), so a rebuild uses exactly this image until it is bumped on
# purpose; the tag alone would follow whatever is pushed under it (OP-191).
FROM python:3.15-slim@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928

# The release version, passed in by the publish workflow. It is not just a
# label: it is written into the package below so /health and the OpenAPI docs
# report the version that is actually running. The default marks a local build.
ARG STATECRAFT_VERSION=0.0.0-dev

# Label the image with metadata
LABEL org.opencontainers.image.title="statecraft" \
      org.opencontainers.image.description="CLI tool and API server for managing Terraform backend resources on AWS" \
      org.opencontainers.image.version="${STATECRAFT_VERSION}" \
      org.opencontainers.image.source="https://github.com/devopsgroupeu/StateCraft" \
      org.opencontainers.image.authors="Andrej Rabek <andrej.rabek@devopsgroup.sk>" \
      org.opencontainers.image.licenses="Apache-2.0"

# No .pyc writes at runtime: the code is root-owned and the root filesystem can
# be read-only, so Python could not write them anyway.
ENV PYTHONDONTWRITEBYTECODE=1

# Set the working directory inside the container
WORKDIR /app

# Debian security fix the pinned base digest does not carry yet. Remove this
# step once Dependabot bumps the digest to a rebuild that includes it.
#   zlib1g: CVE-2026-85091, fixed in 1:1.3.dfsg+really1.3.1-1+deb13u1
RUN apt-get update \
 && apt-get install -y --no-install-recommends --only-upgrade zlib1g \
 && rm -rf /var/lib/apt/lists/*
 
# Non-root user with a fixed UID/GID 1000, matching runAsUser/fsGroup in the
# chart (H97). Without --uid/--gid, --system picks a random UID below 1000.
RUN addgroup --system --gid 1000 appgroup \
 && adduser --system --uid 1000 --ingroup appgroup appuser

# Copy only the lock file first to leverage the Docker layer cache
COPY requirements.txt .

# Install the hash-pinned dependencies (generated from requirements.in with
# pip-compile --generate-hashes). --require-hashes fails the build if any
# downloaded file does not match the lock file.
# Then remove pip itself: it is not used at runtime, and its vendored copies of
# urllib3, msgpack and setuptools are what Trivy flags in the image.
RUN pip install --no-cache-dir --require-hashes -r requirements.txt \
 && pip uninstall -y pip

# Copy the source code. It stays root-owned (read-only for the app user), so a
# compromised process cannot rewrite it.
COPY statecraft/ ./statecraft/

# Stamp the release version into the package. The publish workflow builds from
# the commit that TRIGGERED the release, which is one commit older than
# semantic-release's own `chore(release)` commit - so without this the image
# would always report the previous version.
RUN echo "__version__ = \"${STATECRAFT_VERSION}\"" > ./statecraft/version.py

# Switch to the non-root user (numeric, so the kubelet can verify runAsNonRoot)
USER 1000:1000

# Expose port for API server mode
EXPOSE 8000

# Prometheus metrics, served on their own port so they are never reachable
# through whatever ingress fronts the API port (see statecraft/metrics.py)
EXPOSE 9090

# Entrypoint supports both CLI and server modes
# Server mode: docker run -p 8000:8000 <image> server
# CLI mode: docker run <image> create --region eu-west-1 --bucket-name my-bucket ...
ENTRYPOINT ["python", "-u", "-m", "statecraft.entrypoint"]
CMD ["--help"]
