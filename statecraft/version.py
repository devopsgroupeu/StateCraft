# Single source of the version StateCraft reports at runtime (/health, OpenAPI docs).
#
# Kept in step with the git tag by semantic-release (see .releaserc.json), and
# overwritten again at image build time from the release version (see Dockerfile).
# Both are needed: the Docker build checks out the commit that TRIGGERED the
# release workflow, which is one commit older than semantic-release's own
# `chore(release)` commit - so the file alone would always ship one version behind.
__version__ = "0.6.2"
