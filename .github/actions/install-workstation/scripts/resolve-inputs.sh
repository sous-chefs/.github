#!/usr/bin/env bash
set -euo pipefail

distribution="${CINC_DISTRIBUTION}"
version="${CINC_VERSION}"
channel="${CINC_CHANNEL}"

echo "::group::Resolving Cinc install inputs"
echo "distribution=${distribution}"
echo "version=${version}"
echo "channel=${channel}"
echo "runner_os=${RUNNER_OS:-unknown}"
echo "runner_arch=${RUNNER_ARCH:-unknown}"

case "${distribution}" in
  workstation|cinc-cli)
    ;;
  *)
    echo "::error::distribution must be 'workstation' or 'cinc-cli'." >&2
    exit 1
    ;;
esac

if [ "${distribution}" = "cinc-cli" ] && [ "${RUNNER_OS:-}" != "Linux" ] && [ "${RUNNER_OS:-}" != "macOS" ]; then
  echo "::error::cinc-cli installation currently supports Linux and macOS runners only." >&2
  exit 1
fi

if [ "${distribution}" = "cinc-cli" ] && [ "${version}" = "latest" ]; then
  echo "Resolving latest cinc-cli release with gh."
  if ! command -v gh >/dev/null 2>&1; then
    echo "::error::gh is required to resolve latest cinc-cli release." >&2
    exit 1
  fi

  version="$(gh release view --repo tas50/cinc-cli --json tagName -q .tagName)"
  echo "Resolved cinc-cli latest to ${version}"
fi

{
  echo "distribution=${distribution}"
  echo "requested_version=${version}"
  echo "channel=${channel}"
  echo "runner_os=${RUNNER_OS:-unknown}"
  echo "runner_arch=${RUNNER_ARCH:-unknown}"
} >> "${GITHUB_OUTPUT}"

echo "::endgroup::"
