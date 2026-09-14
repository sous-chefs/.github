# Cookbook OCI publishing

Enable `publish_oci: true` when calling `release-cookbook.yml`. It delegates to
`publish-cookbook-oci.yml`, passing the release tag. OCI failures are non-blocking.

The workflow has three jobs to do:

1. Package the release with `cincproject/workstation:latest`, using the same
   cookbook staging helper as `knife supermarket share`. This preserves
   `chefignore`, generated metadata and cookbook directory layout.
2. Generate SPDX with [Anchore's SBOM action](https://github.com/anchore/sbom-action).
3. Publish with the [official ORAS tooling](https://github.com/oras-project/setup-oras):
   `oras push` for the cookbook and `oras attach` for its SPDX document.

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

This first iteration only packages and pushes. Signing, provenance, registry
registration, immutable-tag enforcement and verification gates are outside this
workflow. Existing Supermarket publishing and Actions archive attestations remain
unchanged.

New GHCR packages start private. Make the package public in GitHub package
settings for anonymous downloads. Publishing the shared workflow must precede
enabling the nginx caller. No live package settings are changed by this code.
