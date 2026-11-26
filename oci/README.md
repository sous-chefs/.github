# Cookbook OCI publishing

Enable `publish_oci: true` when calling `release-cookbook.yml`. It delegates to
`publish-cookbook-oci.yml`, passing the release tag. OCI failures are non-blocking.
To publish only OCI artifacts, also set `supermarket_publisher: none`. The default
continues to publish to Supermarket using Cinc Workstation.

The workflow follows these steps:

1. Package the release with `cincproject/workstation:latest`, using the same
   cookbook staging helper as `knife supermarket share`. This preserves
   `chefignore`, generated metadata and cookbook directory layout.
2. Generate SPDX with [Anchore's SBOM action](https://github.com/anchore/sbom-action).
3. Build the cookbook manifest in a local OCI layout and sign the SPDX inventory
   for its digest with GitHub Actions.
4. Copy the signed cookbook to GHCR by digest, attach the Sigstore bundle and SPDX
   document, then publish the version tag. A signing failure skips the upload.
   An interruption during upload can leave content in GHCR by digest, but the
   workflow sets the release tag only after both attachments succeed.

Actions follow their major versions. Workstation and the tool versions supplied
by the actions can update without changing each cookbook repository.

Cookbooks are published to `ghcr.io/sous-chefs/cookbooks/<name>:<version>`. The OCI
manifest has artifact type `application/vnd.cinc.cookbook.v1+json` and one
`application/vnd.oci.image.layer.v1.tar+gzip` layer. SPDX is a separate
`application/spdx+json` referrer attached to the manifest digest, not an extra
cookbook layer. ORAS supplies the manifest and descriptors; we do not maintain a
custom OCI publisher or require byte-identical manifests with Cinc Registry.

The job summary records the manifest reference. Consumers can use `oras pull` and
`oras discover` to retrieve the cookbook and find its SPDX attachment. Syft reports
the packaged files and software it recognises; it does not resolve Chef cookbook
dependency constraints or describe machines the cookbook might configure.

Callers must grant the publishing job `contents: read`, `packages: write`,
`id-token: write` and `attestations: write`. To verify a new nginx release,
set `DIGEST` to the full `sha256:...` manifest digest in the job summary and run:

```sh
gh attestation verify "oci://ghcr.io/sous-chefs/cookbooks/nginx@$DIGEST" \
  --repo sous-chefs/nginx \
  --signer-workflow sous-chefs/.github/.github/workflows/publish-cookbook-oci.yml \
  --predicate-type https://spdx.dev/Document/v2.3
```

New GHCR packages start private. Make the package public in GitHub package
settings for anonymous downloads. Publishing the shared workflow must precede
enabling the nginx caller. No live package settings are changed by this code.
