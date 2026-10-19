#!/usr/bin/env bash
set -euo pipefail

case "$1" in
  resolve)
    # Cache only Ubuntu installations; preserve the installer on other platforms.
    # shellcheck source=/dev/null
    source "${CINC_OS_RELEASE:-/etc/os-release}"
    if [[ "$ID" != ubuntu ]]; then
      exit 0
    fi
    metadata=$(curl -fsSL --get "https://omnitruck.cinc.sh/${CINC_CHANNEL}/cinc-workstation/metadata" \
      --data-urlencode "p=ubuntu" --data-urlencode "pv=$VERSION_ID" \
      --data-urlencode "m=$(uname -m)" --data-urlencode "v=$CINC_VERSION")
    resolved=$(awk '$1 == "version" {print $2}' <<< "$metadata")
    checksum=$(awk '$1 == "sha256" {print $2}' <<< "$metadata")
    if [[ ! "$resolved" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || [[ ! "$checksum" =~ ^[a-f0-9]{64}$ ]]; then
      echo '::error::Invalid Workstation metadata; refusing to create a cache key.'
      exit 1
    fi
    {
      echo "enabled=true"
      echo "version=$resolved"
      echo "key=cinc-workstation-v1-ubuntu-${VERSION_ID}-$(uname -m)-${CINC_CHANNEL}-${resolved}-${checksum}"
      echo "path=$RUNNER_TEMP/cinc-workstation-cache"
    } >> "$GITHUB_OUTPUT"
    echo "Resolved Cinc Workstation $resolved on Ubuntu $VERSION_ID ($(uname -m))"
    ;;
  pack)
    mkdir -p "$RUNNER_TEMP/cinc-workstation-cache"
    sudo tar -cf "$RUNNER_TEMP/cinc-workstation-cache/workstation.tar" -C /opt cinc-workstation
    sudo chown "$(id -u):$(id -g)" "$RUNNER_TEMP/cinc-workstation-cache/workstation.tar"
    ;;
  restore)
    sudo tar -xf "$RUNNER_TEMP/cinc-workstation-cache/workstation.tar" -C /opt
    # The installer normally creates these links outside /opt.
    for executable in /opt/cinc-workstation/bin/*; do
      [[ -x "$executable" && ! -d "$executable" ]] || continue
      sudo ln -sf "$executable" "/usr/local/bin/$(basename "$executable")"
    done
    # actionshub/test-kitchen and cookbook failure diagnostics use this path.
    sudo ln -sf /opt/cinc-workstation/bin/kitchen /usr/bin/kitchen
    ;;
  *) exit 1 ;;
esac
