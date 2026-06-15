#!/usr/bin/env bash
set -euo pipefail

case "${RUNNER_OS:-}" in
  Linux)
    platform="linux"
    ;;
  macOS)
    platform="darwin"
    ;;
  *)
    echo "::error::cinc-cli installation currently supports Linux and macOS runners only." >&2
    exit 1
    ;;
esac

case "${RUNNER_ARCH:-}" in
  X64)
    arch="amd64"
    ;;
  ARM64)
    arch="arm64"
    ;;
  *)
    echo "::error::Unsupported runner architecture for cinc-cli: ${RUNNER_ARCH:-unknown}" >&2
    exit 1
    ;;
esac

archive="cinc_${CINC_VERSION}_${platform}_${arch}.tar.gz"
url="https://github.com/tas50/cinc-cli/releases/download/${CINC_VERSION}/${archive}"

echo "::group::Installing Cinc CLI ${CINC_VERSION}"
echo "runner_os=${RUNNER_OS:-unknown}"
echo "runner_arch=${RUNNER_ARCH:-unknown}"
echo "platform=${platform}"
echo "arch=${arch}"
echo "installer=${url}"
echo "archive=${RUNNER_TEMP}/${archive}"

curl -fsSL "${url}" -o "${RUNNER_TEMP}/${archive}"
tar -xzf "${RUNNER_TEMP}/${archive}" \
  -C "${RUNNER_TEMP}" \
  --strip-components=1 \
  "cinc_${CINC_VERSION}_${platform}_${arch}/cinc"
sudo install "${RUNNER_TEMP}/cinc" /usr/local/bin/cinc
cinc version
echo "::endgroup::"
