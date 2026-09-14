#!/usr/bin/env python3
"""Real Cinc, ORAS, registry and Cosign qualification; no public publishing."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import time
import uuid

import artifact as a

WORKSTATION = 'cincproject/workstation@sha256:5f0b0005b718eac0b3819ec3b3abe846b620135bc69db269d285be50c5d33f91'
REGISTRY = 'registry@sha256:a3d8aaa63ed8681a604f1dea0aa03f100d5895b6a58ace528858a7b332415373'
HELPERS = Path(__file__).resolve().parent


def command(*args, **kwargs):
    return subprocess.check_output(args, text=True, **kwargs).strip()


def main():
    with tempfile.TemporaryDirectory(prefix='cookbook-oci-') as temporary:
        work = Path(temporary).resolve()
        source = work / 'cookbooks' / 'example'
        source.mkdir(parents=True)
        (source / 'metadata.rb').write_text("name 'example'\nversion '1.2.3'\nlicense 'Apache-2.0'\ndepends 'other', '>= 2.0'\n")
        (source / 'recipes').mkdir()
        (source / 'recipes' / 'default.rb').write_text("log 'OCI fixture'\n")
        (source / 'files').mkdir()
        (source / 'files' / 'run').write_text('#!/bin/sh\necho fixture\n')
        (source / 'files' / 'run').chmod(0o755)
        (source / 'ignored.txt').write_text('excluded by chefignore')
        (source / 'chefignore').write_text('ignored.txt\n')
        (source.parent / 'chefignore').write_text('ignored.txt\n')
        stage = work / 'staged'
        stage.mkdir()

        def cinc(script, *args):
            return command('docker', 'run', '--rm', '--network', 'none',
                           '-v', f'{work}:/work', '-v', f'{HELPERS}:/helpers:ro',
                           WORKSTATION, '/opt/cinc-workstation/embedded/bin/ruby',
                           '/helpers/' + script, *args)

        cinc('stage.rb', '/work/cookbooks/example', 'example', 'v1.2.3', '/work/staged')
        assert not (stage / 'example' / 'ignored.txt').exists(), 'chefignore was not applied'
        assert (stage / 'example' / 'metadata.json').exists()
        rejected = False
        try:
            cinc('stage.rb', '/work/cookbooks/example', 'example', 'v9.9.9', '/work/wrong')
        except subprocess.CalledProcessError:
            rejected = True
        assert rejected, 'version mismatch must fail'

        registry = 'cookbook-oci-' + uuid.uuid4().hex[:10]
        command('docker', 'run', '-d', '--rm', '--name', registry,
                '-p', '127.0.0.1::5000', REGISTRY)
        try:
            port = command('docker', 'port', registry, '5000/tcp').rsplit(':', 1)[1]
            repository = 'localhost:' + port + '/cookbooks/example'
            args = argparse.Namespace(work=work, name='example', tag='v1.2.3',
                                      repository=repository, commit='a' * 40,
                                      source_repository='sous-chefs/example',
                                      workflow_ref='sous-chefs/.github/.github/workflows/release-cookbook.yml@fixture',
                                      workflow_sha='b' * 40)
            a.prepare(args)
            # Compare exact JSON bytes with the independent Cinc Registry ORAS call.
            oracle = subprocess.check_output(['go', 'run', '.', str(work / 'cookbook.tar.gz')],
                                              cwd=HELPERS / 'oracle')
            assert oracle == (work / 'manifest.json').read_bytes(), 'Registry manifest bytes differ'
            command('syft', 'dir:' + str(stage / 'example'), '-o', 'spdx-json=' + str(work / 'syft.spdx.json'),
                    env={**os.environ, 'SYFT_CHECK_FOR_APP_UPDATE': 'false'})
            a.inventory(args)
            first = (work / 'sbom.spdx.json').read_bytes()
            command('syft', 'dir:' + str(stage / 'example'), '-o', 'spdx-json=' + str(work / 'syft.spdx.json'),
                    env={**os.environ, 'SYFT_CHECK_FOR_APP_UPDATE': 'false'})
            a.inventory(args)
            assert first == (work / 'sbom.spdx.json').read_bytes(), 'SBOM is not repeatable'
            # Wait for this disposable registry only, with a bounded deadline.
            for attempt in range(20):
                try:
                    a.push(args)
                    break
                except RuntimeError:
                    if attempt == 19:
                        raise
                    time.sleep(0.25)
            state = json.loads((work / 'state.json').read_text())
            subject = repository + '@' + state['manifest_digest']
            a.anonymous(args)
            assert a.resolve(repository + ':1.2.3') is None, 'tag published before verification'
            a.push(args)
            retried = json.loads((work / 'state.json').read_text())
            assert retried['sbom_attachment'] == state['sbom_attachment'], 'retry duplicated SPDX'
            discovered = json.loads(command('oras', 'discover', '--format', 'json', subject))
            assert state['sbom_attachment'] in [d['digest'] for d in discovered['referrers']]
            for key, filename in [('tarball_digest', 'pulled.tar.gz'), ('sbom_digest', 'pulled.spdx.json')]:
                command('oras', 'blob', 'fetch', '--output', str(work / filename), repository + '@' + state[key])
                assert a.digest((work / filename).read_bytes()) == state[key]
            with tarfile.open(work / 'pulled.tar.gz') as tar:
                assert tar.getmember('example/files/run').mode == 0o755
                tar.extractall(work / 'retrieved', filter='data')
            cinc('load.rb', '/work/retrieved', 'example', '1.2.3')
            for path in (stage / 'example').rglob('*'):
                if path.is_file():
                    assert path.read_bytes() == (work / 'retrieved' / 'example' / path.relative_to(stage / 'example')).read_bytes()
            # Offline disposable key mode tests standard signature storage and the
            # independent verifier, without claiming GitHub OIDC qualification.
            signing_env = {**os.environ, 'COSIGN_PASSWORD': ''}
            command('cosign', 'generate-key-pair', '--output-key-prefix', str(work / 'test'), env=signing_env)
            command('cosign', 'signing-config', 'create', '--out', str(work / 'offline.json'))
            command('cosign', 'sign', '--yes', '--signing-config', str(work / 'offline.json'), '--key', str(work / 'test.key'),
                    subject, env=signing_env)
            command('cosign', 'verify', '--insecure-ignore-tlog', '--key', str(work / 'test.pub'), subject)
            command('cosign', 'generate-key-pair', '--output-key-prefix', str(work / 'wrong'), env=signing_env)
            result = subprocess.run(['cosign', 'verify', '--insecure-ignore-tlog', '--key', str(work / 'wrong.pub'), subject],
                                    capture_output=True)
            assert result.returncode != 0, 'wrong key was accepted'
            a.tag(args)
            assert a.resolve(repository + ':1.2.3') == state['manifest_digest']
            a.push(args)
            # A conflicting version must stop before any new payload is uploaded.
            (stage / 'example' / 'files' / 'run').write_text('changed')
            a.prepare(args)
            a.inventory(args)
            try:
                a.push(args)
            except ValueError:
                pass
            else:
                raise AssertionError('conflicting version was accepted')
            assert a.resolve(repository + ':1.2.3') == state['manifest_digest']
            print('PASS: Cinc staging/extraction, ORAS manifest bytes, repeatable inventory, '
                  'referrers, recovery, version conflicts and independent Cosign verification')
        finally:
            command('docker', 'stop', registry)


if __name__ == '__main__':
    main()
