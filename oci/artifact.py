#!/usr/bin/env python3
"""Cookbook packaging and digest-bound OCI publishing. Python standard library only."""

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile

MANIFEST = 'application/vnd.oci.image.manifest.v1+json'
COOKBOOK = 'application/vnd.cinc.cookbook.v1+json'
LAYER = 'application/vnd.oci.image.layer.v1.tar+gzip'
SPDX = 'application/spdx+json'
EPOCH = '1970-01-01T00:00:00Z'
SLSA = 'https://slsa.dev/provenance/v1'
SPDX_PREDICATE = 'https://spdx.dev/Document/v2.3'


def encode(value):
    return json.dumps(value, separators=(',', ':'), ensure_ascii=False).encode()


def digest(data):
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def descriptor(media_type, data):
    return {'mediaType': media_type, 'digest': digest(data), 'size': len(data)}


def manifest(payload, media_type=LAYER, artifact_type=COOKBOOK, subject=None):
    config = descriptor('application/vnd.oci.empty.v1+json', b'{}')
    config['data'] = 'e30='
    result = {'schemaVersion': 2, 'mediaType': MANIFEST, 'artifactType': artifact_type,
              'config': config, 'layers': [descriptor(media_type, payload)]}
    if subject:
        result['subject'] = subject
    result['annotations'] = {'org.opencontainers.image.created': EPOCH}
    return encode(result)


def archive(root, target):
    # GNU tar format matches cookbook consumers; gzip has no filename or clock.
    with target.open('wb') as raw, gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode='w', format=tarfile.GNU_FORMAT) as tar:
            for path in [root, *sorted(root.rglob('*'))]:
                if path.is_symlink() or not (path.is_file() or path.is_dir()):
                    raise ValueError(f'Unsupported staged file: {path}')
                info = tar.gettarinfo(str(path), arcname=str(path.relative_to(root.parent)))
                info.uid = info.gid = info.mtime = 0
                info.uname = info.gname = ''
                if path.is_file():
                    with path.open('rb') as source:
                        tar.addfile(info, source)
                else:
                    tar.addfile(info)


def output(**values):
    with open(os.environ.get('GITHUB_OUTPUT', os.devnull), 'a') as stream:
        for key, value in values.items():
            if '\n' in str(value):
                raise ValueError('Multiline output is not supported')
            stream.write(f'{key}={value}\n')


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def prepare(args):
    root = args.work / 'staged' / args.name
    metadata = json.loads((root / 'metadata.json').read_text())
    version = metadata['version']
    if metadata['name'] != args.name or args.tag not in (version, 'v' + version):
        raise ValueError('Cookbook name/version does not match release')
    if not re.fullmatch(r'[a-z0-9_][a-z0-9_-]*', args.name):
        raise ValueError('Invalid cookbook name')
    tarball = args.work / 'cookbook.tar.gz'
    archive(root, tarball)
    data = tarball.read_bytes()
    raw = manifest(data)
    (args.work / 'manifest.json').write_bytes(raw)
    (args.work / 'empty.json').write_bytes(b'{}')
    state = {'name': args.name, 'version': version, 'repository': args.repository,
             'source_commit': args.commit, 'source_repository': args.source_repository,
             'source_tag': args.tag, 'manifest_digest': digest(raw),
             'tarball_digest': digest(data), 'workflow_ref': args.workflow_ref,
             'workflow_sha': args.workflow_sha}
    (args.work / 'state.json').write_bytes(encode(state))
    output(repository=args.repository, manifest_digest=digest(raw), version=version)


def inventory(args):
    state = json.loads((args.work / 'state.json').read_text())
    root = args.work / 'staged' / state['name']
    metadata = json.loads((root / 'metadata.json').read_text())
    sbom = json.loads((args.work / 'syft.spdx.json').read_text())
    if sbom['spdxVersion'] != 'SPDX-2.3':
        raise ValueError('Expected SPDX 2.3')
    # Syft's clock and temporary scan path must not change the inventory identity.
    sbom['name'] = f"{state['name']}-{state['version']}"
    sbom['documentNamespace'] = 'https://sous-chefs.org/spdx/' + state['manifest_digest'].replace(':', '-')
    sbom['creationInfo']['created'] = EPOCH
    package_id = 'SPDXRef-Cookbook'
    package = {'SPDXID': package_id, 'name': state['name'], 'versionInfo': state['version'],
               'downloadLocation': 'NOASSERTION', 'filesAnalyzed': False,
               'licenseConcluded': 'NOASSERTION', 'licenseDeclared': 'NOASSERTION',
               'copyrightText': 'NOASSERTION',
               'checksums': [{'algorithm': 'SHA256', 'checksumValue': state['tarball_digest'][7:]}],
               'comment': 'Cookbook metadata declarations: ' + json.dumps({
                   'license': metadata.get('license'), 'dependencies': metadata.get('dependencies', {}),
                   'source_url': metadata.get('source_url')}, sort_keys=True)}
    # The raw declaration can be free text, so do not mislabel it as an SPDX expression.
    roots = {p['SPDXID'] for p in sbom.get('packages', [])
             if p['SPDXID'].startswith('SPDXRef-DocumentRoot-Directory-')}
    sbom['packages'] = [p for p in sbom.get('packages', []) if p['SPDXID'] not in roots] + [package]
    relationships = sbom.setdefault('relationships', [])
    for relationship in relationships:
        for field in ['spdxElementId', 'relatedSpdxElement']:
            if relationship[field] in roots:
                relationship[field] = package_id
    relationships.append({'spdxElementId': sbom['SPDXID'], 'relationshipType': 'DESCRIBES',
                          'relatedSpdxElement': package_id})
    for name, constraint in sorted(metadata.get('dependencies', {}).items()):
        identifier = 'SPDXRef-DeclaredDependency-' + hashlib.sha256(name.encode()).hexdigest()
        sbom['packages'].append({'SPDXID': identifier, 'name': name,
                                 'downloadLocation': 'NOASSERTION', 'filesAnalyzed': False,
                                 'licenseConcluded': 'NOASSERTION', 'licenseDeclared': 'NOASSERTION',
                                 'copyrightText': 'NOASSERTION',
                                 'comment': f'Declared cookbook dependency constraint: {constraint}. '
                                            'Not resolved or bundled by this build.'})
        relationships.append({'spdxElementId': package_id, 'relationshipType': 'DEPENDS_ON',
                              'relatedSpdxElement': identifier})
    # Ensure Ruby-only cookbooks still have a complete file inventory even if
    # the scanner does not recognise a package ecosystem in their contents.
    old_files = {f['SPDXID'] for f in sbom.get('files', [])}
    sbom['files'] = []
    relationships[:] = [r for r in relationships if not (
        r['spdxElementId'] in old_files or r['relatedSpdxElement'] in old_files)]
    for path in sorted(root.rglob('*')):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        identifier = 'SPDXRef-CookbookFile-' + hashlib.sha256(relative.encode()).hexdigest()
        sbom['files'].append({'SPDXID': identifier, 'fileName': './' + relative,
                              'checksums': [{'algorithm': 'SHA256',
                                             'checksumValue': digest(path.read_bytes())[7:]}],
                              'licenseConcluded': 'NOASSERTION',
                              'copyrightText': 'NOASSERTION'})
        relationships.append({'spdxElementId': package_id, 'relationshipType': 'CONTAINS',
                              'relatedSpdxElement': identifier})
    data = encode(sbom)
    (args.work / 'sbom.spdx.json').write_bytes(data)
    state.update(sbom_digest=digest(data))
    (args.work / 'state.json').write_bytes(encode(state))
    predicate = {
        'buildDefinition': {
            'buildType': 'https://github.com/sous-chefs/.github/oci/cookbook/v1',
            'externalParameters': {'source': state['source_repository'], 'tag': state['source_tag']},
            'internalParameters': {},
            'resolvedDependencies': [
                {'uri': 'git+https://github.com/' + state['source_repository'],
                 'digest': {'gitCommit': state['source_commit']}},
                {'uri': 'https://github.com/' + state['workflow_ref'],
                 'digest': {'gitCommit': state['workflow_sha']}},
                {'uri': 'cookbook.tar.gz', 'digest': {'sha256': state['tarball_digest'][7:]}},
                {'uri': 'sbom.spdx.json', 'digest': {'sha256': state['sbom_digest'][7:]}}]},
        'runDetails': {'builder': {'id': 'https://github.com/' + state['workflow_ref']},
                       'metadata': {'invocationId': os.environ.get('GITHUB_SERVER_URL', 'https://github.com')
                                    + '/' + state['source_repository'] + '/actions/runs/'
                                    + os.environ.get('GITHUB_RUN_ID', 'local')}}}
    (args.work / 'provenance.json').write_bytes(encode(predicate))
    output(sbom_digest=state['sbom_digest'])


def resolve(reference):
    result = subprocess.run(['oras', 'manifest', 'fetch', '--descriptor', reference],
                            capture_output=True, text=True)
    if result.returncode:
        # Only a registry's explicit missing-manifest result permits first publish.
        if 'not found' in result.stderr.lower() or 'manifest_unknown' in result.stderr.lower():
            return None
        raise RuntimeError(result.stderr)
    return json.loads(result.stdout)['digest']


def check_tag(state):
    existing = resolve(state['repository'] + ':' + state['version'])
    if existing and existing != state['manifest_digest']:
        raise ValueError('Version tag already points to another manifest; refusing overwrite')


def push(args):
    state = json.loads((args.work / 'state.json').read_text())
    check_tag(state)
    repo = state['repository']
    for filename, media in [('empty.json', 'application/vnd.oci.empty.v1+json'),
                            ('cookbook.tar.gz', LAYER), ('sbom.spdx.json', SPDX)]:
        run('oras', 'blob', 'push', '--media-type', media, repo, str(args.work / filename))
    run('oras', 'manifest', 'push', repo + '@' + state['manifest_digest'], str(args.work / 'manifest.json'))
    # ORAS attach maintains native referrers or its supported index-tag fallback.
    # Use a stable title to prevent temporary paths entering descriptor identity.
    annotations = {'$manifest': {'org.opencontainers.image.created': EPOCH},
                   str(args.work / 'sbom.spdx.json'): {'org.opencontainers.image.title': 'sbom.spdx.json'}}
    (args.work / 'annotations.json').write_bytes(encode(annotations))
    result = run('oras', 'attach', '--disable-path-validation', '--format', 'json', '--artifact-type', SPDX,
                 '--annotation-file', str(args.work / 'annotations.json'),
                 repo + '@' + state['manifest_digest'], str(args.work / 'sbom.spdx.json') + ':' + SPDX)
    state['sbom_attachment'] = json.loads(result)['digest']
    (args.work / 'state.json').write_bytes(encode(state))


def validate_statement(statement, state, predicate_type, expected):
    subjects = statement.get('subject', [])
    if not any(s.get('name') == state['repository'] and
               s.get('digest', {}).get('sha256') == state['manifest_digest'][7:] for s in subjects):
        raise ValueError('Attestation subject mismatch')
    if statement.get('predicateType') != predicate_type:
        raise ValueError('Attestation predicate type mismatch')
    actual = statement['predicate']
    if predicate_type == SLSA:
        # Invocation metadata may differ on a recovery run; all build inputs must match.
        if actual.get('buildDefinition') != expected['buildDefinition']:
            raise ValueError('Provenance build inputs mismatch')
    elif actual != expected:
        raise ValueError('Attested SPDX differs from the retrieved inventory')


def verify_evidence(state, work, kind):
    subject = state['repository'] + '@' + state['manifest_digest']
    if kind == 'signature':
        run('cosign', 'verify', '--certificate-identity', 'https://github.com/' + state['workflow_ref'],
            '--certificate-github-workflow-repository', state['source_repository'],
            '--certificate-oidc-issuer', 'https://token.actions.githubusercontent.com', subject)
        return
    predicate, filename = {'provenance': (SLSA, 'provenance.json'),
                           'sbom': (SPDX_PREDICATE, 'sbom.spdx.json')}[kind]
    verified = json.loads(run('gh', 'attestation', 'verify', 'oci://' + subject,
                              '--bundle-from-oci',
                              '--repo', state['source_repository'],
                              '--signer-workflow', state['workflow_ref'].split('@')[0],
                              '--signer-digest', state['workflow_sha'],
                              '--predicate-type', predicate, '--format', 'json'))
    expected = json.loads((work / filename).read_text())
    for item in verified:
        try:
            validate_statement(item['verificationResult']['statement'], state, predicate, expected)
            return
        except (ValueError, KeyError):
            continue
    raise ValueError('No verified attestation matches the expected release inputs')


def evidence(args):
    state = json.loads((args.work / 'state.json').read_text())
    for kind in ['signature', 'provenance', 'sbom']:
        try:
            verify_evidence(state, args.work, kind)
            present = 'true'
        except (subprocess.CalledProcessError, ValueError):
            present = 'false'
        output(**{kind: present})


def verify(args):
    state = json.loads((args.work / 'state.json').read_text())
    repo = state['repository']
    subject = repo + '@' + state['manifest_digest']
    raw = subprocess.check_output(['oras', 'manifest', 'fetch', subject])
    if raw != (args.work / 'manifest.json').read_bytes():
        raise ValueError('Retrieved manifest bytes differ')
    for key, filename in [('tarball_digest', 'cookbook.tar.gz'), ('sbom_digest', 'sbom.spdx.json')]:
        target = args.work / ('retrieved-' + filename)
        run('oras', 'blob', 'fetch', '--output', str(target), repo + '@' + state[key])
        if digest(target.read_bytes()) != state[key]:
            raise ValueError('Retrieved blob digest mismatch')
    discovered = json.loads(run('oras', 'discover', '--format', 'json', subject))
    if state['sbom_attachment'] not in [d['digest'] for d in discovered.get('referrers', [])]:
        raise ValueError('SPDX referrer is not discoverable')
    attachment_raw = subprocess.check_output([
        'oras', 'manifest', 'fetch', repo + '@' + state['sbom_attachment']])
    if digest(attachment_raw) != state['sbom_attachment']:
        raise ValueError('SPDX attachment manifest digest mismatch')
    attachment = json.loads(attachment_raw)
    if (attachment.get('artifactType') != SPDX or
            attachment.get('subject', {}).get('digest') != state['manifest_digest'] or
            [layer['digest'] for layer in attachment['layers']] != [state['sbom_digest']]):
        raise ValueError('SPDX attachment does not bind the expected inventory to this cookbook')
    for kind in ['signature', 'provenance', 'sbom']:
        verify_evidence(state, args.work, kind)
    with tarfile.open(args.work / 'retrieved-cookbook.tar.gz') as tar:
        tar.extractall(args.work / 'retrieved', filter='data')


def tag(args):
    state = json.loads((args.work / 'state.json').read_text())
    subject = state['repository'] + '@' + state['manifest_digest']
    # Check again immediately before tagging. Workflow concurrency serialises all
    # releases in the caller repository; GHCR itself does not offer compare-and-swap.
    check_tag(state)
    run('oras', 'tag', subject, state['version'])
    output(reference=subject)


def anonymous(args):
    state = json.loads((args.work / 'state.json').read_text())
    subject = state['repository'] + '@' + state['manifest_digest']
    with tempfile.TemporaryDirectory() as temporary:
        config = Path(temporary) / 'config.json'
        config.write_text('{"auths":{}}')
        for reference in [subject, state['repository'] + '@' + state['sbom_attachment']]:
            run('oras', 'manifest', 'fetch', '--registry-config', str(config), reference)
        run('oras', 'discover', '--registry-config', str(config), '--format', 'json', subject)
        for key in ['tarball_digest', 'sbom_digest']:
            target = Path(temporary) / key
            run('oras', 'blob', 'fetch', '--registry-config', str(config), '--output', str(target),
                state['repository'] + '@' + state[key])
            if digest(target.read_bytes()) != state[key]:
                raise ValueError('Anonymous download digest mismatch')
    output(reference=subject)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'inventory', 'push', 'evidence', 'verify', 'tag', 'anonymous'])
    parser.add_argument('--work', type=Path, required=True)
    for name in ['name', 'tag', 'repository', 'commit', 'source-repository', 'workflow-ref', 'workflow-sha']:
        parser.add_argument('--' + name)
    args = parser.parse_args()
    globals()[args.command](args)


if __name__ == '__main__':
    main()
