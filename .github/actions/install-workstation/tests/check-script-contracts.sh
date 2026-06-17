#!/usr/bin/env bash
set -euo pipefail

action_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
action_file="${action_dir}/action.yml"
scripts_dir="${action_dir}/scripts"

assert_contains() {
  local file="$1"
  local pattern="$2"

  echo "Checking ${file} contains: ${pattern}"
  if ! grep -Fq -- "${pattern}" "${file}"; then
    echo "::error file=${file}::Expected to find: ${pattern}" >&2
    return 1
  fi
}

assert_output() {
  local file="$1"
  local key="$2"
  local expected="$3"

  echo "Checking ${file} output ${key}=${expected}"
  if ! grep -Fxq -- "${key}=${expected}" "${file}"; then
    echo "::error file=${file}::Expected output ${key}=${expected}" >&2
    echo "Actual outputs:" >&2
    sed -n '1,120p' "${file}" >&2
    return 1
  fi
}

run_outputs_unix_contract() {
  local distribution="$1"
  local expected_version="$2"
  local expected_executable="$3"

  local tmpdir
  tmpdir="$(mktemp -d)"
  trap 'rm -rf "${tmpdir}"' RETURN

  mkdir -p "${tmpdir}/bin"

  cat > "${tmpdir}/bin/cinc" <<'EOF'
#!/usr/bin/env bash
case "${1:-}" in
  --version|version)
    echo "cinc 0.11.0"
    ;;
  *)
    echo "unexpected cinc arguments: $*" >&2
    exit 1
    ;;
esac
EOF

  cat > "${tmpdir}/bin/chef" <<'EOF'
#!/usr/bin/env bash
case "${1:-}" in
  --version|version)
    echo "Redirecting to cinc" >&2
    echo "Cinc Workstation version: 25.0.0"
    ;;
  *)
    echo "unexpected chef arguments: $*" >&2
    exit 1
    ;;
esac
EOF

  cat > "${tmpdir}/bin/knife" <<'EOF'
#!/usr/bin/env bash
echo "knife 25.0.0"
EOF

  chmod +x "${tmpdir}/bin/cinc" "${tmpdir}/bin/chef" "${tmpdir}/bin/knife"

  local output_file="${tmpdir}/outputs"
  PATH="${tmpdir}/bin:${PATH}" \
    GITHUB_OUTPUT="${output_file}" \
    CINC_DISTRIBUTION="${distribution}" \
    bash "${scripts_dir}/outputs-unix.sh"

  assert_output "${output_file}" "distribution" "${distribution}"
  assert_output "${output_file}" "version" "${expected_version}"
  assert_output "${output_file}" "executable" "${expected_executable}"
  assert_output "${output_file}" "executable_path" "${tmpdir}/bin/${expected_executable}"
  assert_output "${output_file}" "cinc_path" "${tmpdir}/bin/cinc"
  assert_output "${output_file}" "chef_path" "${tmpdir}/bin/chef"
  assert_output "${output_file}" "knife_path" "${tmpdir}/bin/knife"
}

run_resolve_inputs_contract() {
  local distribution="$1"
  local version="$2"
  local expected_version="$3"

  local tmpdir
  tmpdir="$(mktemp -d)"
  trap 'rm -rf "${tmpdir}"' RETURN

  mkdir -p "${tmpdir}/bin"

  cat > "${tmpdir}/bin/gh" <<'EOF'
#!/usr/bin/env bash
if [ "$*" = "release view --repo tas50/cinc-cli --json tagName -q .tagName" ]; then
  echo "v9.9.9"
  exit 0
fi

echo "unexpected gh arguments: $*" >&2
exit 1
EOF

  chmod +x "${tmpdir}/bin/gh"

  local output_file="${tmpdir}/outputs"
  PATH="${tmpdir}/bin:${PATH}" \
    GITHUB_OUTPUT="${output_file}" \
    RUNNER_OS="Linux" \
    RUNNER_ARCH="X64" \
    CINC_DISTRIBUTION="${distribution}" \
    CINC_VERSION="${version}" \
    CINC_CHANNEL="stable" \
    bash "${scripts_dir}/resolve-inputs.sh"

  assert_output "${output_file}" "distribution" "${distribution}"
  assert_output "${output_file}" "requested_version" "${expected_version}"
  assert_output "${output_file}" "channel" "stable"
  assert_output "${output_file}" "runner_os" "Linux"
  assert_output "${output_file}" "runner_arch" "X64"
}

echo "::group::Checking install-workstation action contract"
echo "action_file=${action_file}"
echo "scripts_dir=${scripts_dir}"

# Keep action.yml as orchestration. Implementation should stay in scripts so
# Bash linting, PowerShell parsing, and focused contract tests can run directly.
assert_contains "${action_file}" "\$GITHUB_ACTION_PATH/scripts/install-unix.sh"
assert_contains "${action_file}" "\$GITHUB_ACTION_PATH/scripts/install-cinc-cli.sh"
assert_contains "${action_file}" "\$GITHUB_ACTION_PATH/scripts/outputs-unix.sh"
assert_contains "${action_file}" "\$env:GITHUB_ACTION_PATH/scripts/install-windows.ps1"
assert_contains "${action_file}" "\$env:GITHUB_ACTION_PATH/scripts/refresh-windows-path.ps1"
assert_contains "${action_file}" "\$env:GITHUB_ACTION_PATH/scripts/outputs-windows.ps1"
assert_contains "${action_file}" "outputs:"
assert_contains "${action_file}" "version:"
assert_contains "${action_file}" "executable:"
assert_contains "${action_file}" "executable_path:"
assert_contains "${action_file}" "cinc_path:"
assert_contains "${action_file}" "chef_path:"
assert_contains "${action_file}" "knife_path:"
assert_contains "${action_file}" "runner_os:"
assert_contains "${action_file}" "runner_arch:"
assert_contains "${action_file}" "steps.outputs-unix.outputs.version || steps.outputs-windows.outputs.version"

for script in "${scripts_dir}"/*.sh; do
  assert_contains "${script}" "#!/usr/bin/env bash"
  assert_contains "${script}" "set -euo pipefail"
done

for script in "${scripts_dir}"/*.ps1; do
  assert_contains "${script}" "Set-StrictMode -Version Latest"
  assert_contains "${script}" "\$ErrorActionPreference = 'Stop'"
done

assert_contains "${scripts_dir}/install-unix.sh" "-P cinc-workstation"
assert_contains "${scripts_dir}/install-windows.ps1" "-project cinc-workstation"
assert_contains "${scripts_dir}/install-cinc-cli.sh" "platform=\"darwin\""
assert_contains "${scripts_dir}/install-cinc-cli.sh" "platform=\"linux\""
assert_contains "${scripts_dir}/install-cinc-cli.sh" "arch=\"amd64\""
assert_contains "${scripts_dir}/install-cinc-cli.sh" "arch=\"arm64\""
assert_contains "${scripts_dir}/resolve-inputs.sh" "gh release view --repo tas50/cinc-cli"
assert_contains "${scripts_dir}/refresh-windows-path.ps1" "\$env:GITHUB_PATH"
assert_contains "${scripts_dir}/outputs-unix.sh" "emit_output \"version\""
assert_contains "${scripts_dir}/outputs-unix.sh" "emit_output \"executable\""
assert_contains "${scripts_dir}/outputs-unix.sh" "emit_output \"executable_path\""
assert_contains "${scripts_dir}/outputs-unix.sh" "emit_output \"knife_path\""
assert_contains "${scripts_dir}/outputs-windows.ps1" "Add-ActionOutput -Name version"
assert_contains "${scripts_dir}/outputs-windows.ps1" "Add-ActionOutput -Name executable"
assert_contains "${scripts_dir}/outputs-windows.ps1" "Add-ActionOutput -Name executable_path"
assert_contains "${scripts_dir}/outputs-windows.ps1" "Add-ActionOutput -Name knife_path"

echo "::endgroup::"

echo "::group::Checking install-workstation output contracts"
run_resolve_inputs_contract "workstation" "latest" "latest"
run_resolve_inputs_contract "cinc-cli" "latest" "v9.9.9"
run_outputs_unix_contract "workstation" "Cinc Workstation version: 25.0.0" "chef"
run_outputs_unix_contract "cinc-cli" "cinc 0.11.0" "cinc"
echo "::endgroup::"
