# Signed cookbook OCI publishing

`release-cookbook.yml` accepts `publish_oci: true`. It defaults to false. The
first pilot is nginx; normal Chef Supermarket publishing and existing Actions
archive attestations continue independently. OCI errors produce a warning and
step summary without failing the release. A failed OCI path stops before later
OCI steps; it never substitutes an unsigned artifact for a verified one.

## Artifact format

The public repository is `ghcr.io/sous-chefs/cookbooks/<cookbook>`. Cookbook
metadata supplies the version tag, without a leading `v`. The Git release tag
must equal that version or `v<version>`. The OCI checkout explicitly resolves
`refs/tags/<release_tag>`; provenance records its actual commit, including during
release recovery.

The artifact is an OCI 1.1 image manifest with:

- `artifactType`: `application/vnd.cinc.cookbook.v1+json`.
- One payload layer: `application/vnd.oci.image.layer.v1.tar+gzip`.
- ORAS-compatible empty JSON config, including its inline `e30=` data.
- Only the fixed `org.opencontainers.image.created=1970-01-01T00:00:00Z`
  manifest annotation. This is a reproducibility marker, not the publication time.
- No layer annotations. The manifest JSON encoding is checked against
  `oras-go v2.6.1` with Cinc Registry's `PackManifestVersion1_1` options.

The layer contains a Supermarket-compatible cookbook root directory and generated
`metadata.json`. `stage.rb` uses the loader, validation and staging helper used by
`knife supermarket share`, including `chefignore`. Packaging preserves staged
file modes and normalises ownership, timestamps, ordering and gzip headers.
Validation runs without publishing credentials or container network access.

The **manifest digest** is the cookbook's canonical OCI identity. The compressed
tarball SHA-256 and exact SPDX document SHA-256 are separate identities. All three
are recorded in the job summary. This does not claim that a separately generated
Supermarket gzip archive has the same compressed bytes.

## Evidence and trust

The pinned Syft scan examines staged cookbook contents. The SPDX 2.3 document adds
the cookbook, every packaged file's SHA-256, declared licence text and declared
dependency constraints. Unresolved dependencies are labelled as declarations and
are not represented as bundled, resolved versions. A scan of a cookbook does not
describe the eventual operating system it configures.

Evidence is separate from the single cookbook payload layer:

- Raw SPDX uses `application/spdx+json`, attached to the cookbook manifest with
  ORAS. Its stable filename annotation is `sbom.spdx.json`.
- A GitHub SPDX attestation signs the inventory with the cookbook manifest as subject.
- A GitHub SLSA v1 attestation records the actual release commit, executing workflow
  commit, tarball digest and SPDX digest. Its build type is
  `https://github.com/sous-chefs/.github/oci/cookbook/v1`. This is a custom packaging
  predicate, not a claim of a particular SLSA assurance level.
- Cosign signs the cookbook manifest digest using GitHub OIDC and Sigstore.

The helper checkout uses `job_workflow_sha` from GitHub's authenticated OIDC token
endpoint. Helpers therefore come from the commit executing the reusable workflow,
not the caller checkout or the shared repository's current default branch.

Verification requires the GitHub issuer, the expected cookbook source repository,
the shared signing workflow and its expected commit. GitHub attestations are read
**from OCI** with `--bundle-from-oci`, not merely found in GitHub's API. The
provenance predicate is also compared with the actual expected release inputs.
These are CI publishing assertions. They are distinct from Cinc Registry's
separate acceptance signature and do not claim that the code is safe.

ORAS uses native OCI referrers where supported and its referrer-index tag fallback
otherwise. Cosign and GitHub use their standard registry evidence formats. The
local registry test exercises fallback discovery; actual GHCR/OIDC qualification
remains a required pilot check.

## Recovery and rollout

The workflow publishes payloads by digest, attaches and independently verifies
evidence, reloads the retrieved cookbook in Cinc, then publishes the version tag.
An existing matching digest can be retried; verified matching signatures and
attestations are reused. A different existing version digest is rejected. The
workflow checks before upload and immediately before tagging and serialises OCI
jobs per source repository. GHCR has no compare-and-swap tag operation: keep other
writers out of this package; the workflow cannot enforce immutability against an
independent writer with package write access.

For the pilot:

1. Publish the shared workflow commit. Update nginx's caller to that immutable
   commit with `publish_oci: true` before enabling the pilot.
2. Confirm the caller grants `contents: read`, `packages: write`,
   `attestations: write` and `id-token: write` to the OCI job. Existing release
   management permissions remain at the caller level.
3. Let a normal nginx release run. GHCR publishing uses its `GITHUB_TOKEN` and
   links the package to the caller repository. Confirm that link in package settings.
4. Make the new GHCR package public in its package settings. New packages default
   to private. The anonymous-read step deliberately reports incomplete publication
   until that setting is applied. Re-run only the OCI job after changing visibility;
   do not re-run Supermarket publishing just to repair this check.
5. Confirm anonymous manifest, tarball, SPDX and referrer retrieval plus the
   verification commands below. Keep the pilot non-blocking. Adopt other callers
   only after this check succeeds.

See [GitHub package visibility and authentication](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).
No package visibility setting or release is changed by the local test suite.

Rollback is `publish_oci: false` or the previous caller pin. Retain published
digests and evidence. No historical backfill or Cinc ingestion/registration is
implemented; publishing here does not replace Cinc-owned storage or deploy a registry.

## Independent verification

Use ORAS 1.3.4, Cosign 3.1.3 and a GitHub CLI supporting `--bundle-from-oci`.
Obtain the expected manifest digest, shared workflow reference and full workflow
commit from the release record you trust, not from an arbitrary attached signature.
Replace the example values before running:

```bash
repository=ghcr.io/sous-chefs/cookbooks/nginx
digest=sha256:RELEASE_MANIFEST_DIGEST
workflow=sous-chefs/.github/.github/workflows/release-cookbook.yml
workflow_ref=FULL_SHARED_WORKFLOW_COMMIT
subject="$repository@$digest"

oras manifest fetch "$subject"
oras discover --format json "$subject"
cosign verify "$subject" \
  --certificate-identity "https://github.com/$workflow@$workflow_ref" \
  --certificate-github-workflow-repository sous-chefs/nginx \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
gh attestation verify "oci://$subject" --bundle-from-oci \
  --repo sous-chefs/nginx --signer-workflow "$workflow" \
  --signer-digest "$workflow_ref" --predicate-type https://slsa.dev/provenance/v1 \
  --format json
gh attestation verify "oci://$subject" --bundle-from-oci \
  --repo sous-chefs/nginx --signer-workflow "$workflow" \
  --signer-digest "$workflow_ref" --predicate-type https://spdx.dev/Document/v2.3 \
  --format json
```

Use `oras blob fetch --output cookbook.tar.gz "$repository@<layer-digest>"` to
retrieve the cookbook layer identified by the manifest. Fetch the SPDX referrer's
manifest, check its `subject.digest`, then fetch its layer the same way. Check both
blob hashes against their descriptors and the verified provenance. Compare the
verified SPDX predicate with the retrieved document. Extract into a new directory
and load the cookbook with Cinc. `artifact.py verify` performs these checks for a
workflow's recorded state; `anonymous` repeats the public reads with an empty
registry credential configuration.

## Local qualification

```bash
python3 -m unittest discover -s oci -p 'test_*.py' -v
python3 oci/integration.py
```

Integration requires Docker, Python 3.12+, Go 1.25+, ORAS, Syft and Cosign at the
workflow's pinned versions. Missing tools fail the test. It starts and removes a
disposable localhost registry, uses a generated cookbook and disposable keys, and
never publishes to GHCR or a public transparency log. Its offline signing config
and relaxed transparency-log check are test-only; the production verifier keeps
the normal Sigstore checks. The test is not a substitute for live GitHub OIDC
verification.
