#!/usr/bin/env bash
set -euo pipefail

echo "::group::Installing Cinc Workstation v${CINC_VERSION}"
echo "channel=${CINC_CHANNEL}"
echo "installer=https://omnitruck.cinc.sh/install.sh"
curl -fsSL https://omnitruck.cinc.sh/install.sh |
  sudo bash -s -- -P cinc-workstation -c "${CINC_CHANNEL}" -v "${CINC_VERSION}"
echo "::endgroup::"
