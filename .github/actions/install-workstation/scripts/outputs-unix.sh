#!/usr/bin/env bash
set -euo pipefail

resolve_command() {
  local command_name="$1"

  command -v "${command_name}" 2>/dev/null || true
}

emit_output() {
  local key="$1"
  local value="$2"

  printf '%s=%s\n' "${key}" "${value}" >> "${GITHUB_OUTPUT}"
}

cinc_path="$(resolve_command cinc)"
chef_path="$(resolve_command chef)"
knife_path="$(resolve_command knife)"

case "${CINC_DISTRIBUTION}" in
  workstation)
    if [ -n "${chef_path}" ]; then
      executable="chef"
      executable_path="${chef_path}"
    else
      executable="cinc"
      executable_path="${cinc_path}"
    fi
    ;;
  cinc-cli)
    executable="cinc"
    executable_path="${cinc_path}"
    ;;
  *)
    echo "::error::Unsupported distribution for output resolution: ${CINC_DISTRIBUTION}" >&2
    exit 1
    ;;
esac

if [ -z "${executable_path}" ]; then
  echo "::error::Could not find ${executable} in PATH." >&2
  exit 1
fi

version_output="$("${executable_path}" --version 2>/dev/null || "${executable_path}" version)"
version="$(printf '%s\n' "${version_output}" | head -n 1)"

echo "::group::Resolved Cinc action outputs"
echo "distribution=${CINC_DISTRIBUTION}"
echo "executable=${executable}"
echo "executable_path=${executable_path}"
echo "cinc_path=${cinc_path}"
echo "chef_path=${chef_path}"
echo "knife_path=${knife_path}"
echo "version=${version}"

emit_output "distribution" "${CINC_DISTRIBUTION}"
emit_output "executable" "${executable}"
emit_output "executable_path" "${executable_path}"
emit_output "cinc_path" "${cinc_path}"
emit_output "chef_path" "${chef_path}"
emit_output "knife_path" "${knife_path}"
emit_output "version" "${version}"
echo "::endgroup::"
