"""Run with python3 -m unittest discover -s oci -p 'test_*.py'."""
import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import artifact as a


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.root = self.work / 'staged' / 'example'
        self.root.mkdir(parents=True)
        (self.root / 'metadata.json').write_text(json.dumps({
            'name': 'example', 'version': '1.2.3', 'license': 'Apache-2.0',
            'dependencies': {'other': '>= 2.0'}}))
        (self.root / 'run').write_text('#!/bin/sh\necho hello\n')
        (self.root / 'run').chmod(0o755)
        self.args = argparse.Namespace(work=self.work, name='example', tag='v1.2.3',
                                       repository='ghcr.io/sous-chefs/cookbooks/example',
                                       commit='a' * 40, source_repository='sous-chefs/example',
                                       workflow_ref='sous-chefs/.github/.github/workflows/release-cookbook.yml@v10',
                                       workflow_sha='b' * 40)
        a.prepare(self.args)
        self.syft = {'spdxVersion': 'SPDX-2.3', 'SPDXID': 'SPDXRef-DOCUMENT',
                     'creationInfo': {'created': 'now', 'creators': ['Tool: syft']},
                     'packages': [{'SPDXID': 'SPDXRef-DocumentRoot-Directory-/temporary/path',
                                   'name': '/temporary/path'}],
                     'files': [{'SPDXID': 'arbitrary-file-id'}],
                     'relationships': [{'spdxElementId': 'SPDXRef-DocumentRoot-Directory-/temporary/path',
                                        'relationshipType': 'CONTAINS', 'relatedSpdxElement': 'arbitrary-file-id'}]}
        self.inventory()

    def inventory(self):
        (self.work / 'syft.spdx.json').write_text(json.dumps(self.syft))
        a.inventory(self.args)
        return (self.work / 'sbom.spdx.json').read_bytes()

    def state(self):
        return json.loads((self.work / 'state.json').read_text())

    def test_archive_reproducible_and_preserves_executable(self):
        original = (self.work / 'cookbook.tar.gz').read_bytes()
        os.utime(self.root / 'run', (12345, 12345))
        a.archive(self.root, self.work / 'second.tar.gz')
        self.assertEqual(original, (self.work / 'second.tar.gz').read_bytes())
        with tarfile.open(self.work / 'second.tar.gz') as tar:
            self.assertEqual(tar.getmember('example/run').mode, 0o755)
            self.assertEqual(tar.getmember('example/run').mtime, 0)
            self.assertIn('example/metadata.json', tar.getnames())

    def test_rejects_tag_or_name_mismatch(self):
        self.args.tag = 'v9.0.0'
        with self.assertRaises(ValueError):
            a.prepare(self.args)
        self.args.tag = 'v1.2.3'
        metadata = self.root / 'metadata.json'
        metadata.write_text('{"name":"other","version":"1.2.3"}')
        with self.assertRaises(ValueError):
            a.prepare(self.args)

    def test_single_layer_and_three_distinct_digests(self):
        manifest = json.loads((self.work / 'manifest.json').read_bytes())
        self.assertEqual(manifest['artifactType'], a.COOKBOOK)
        self.assertEqual(len(manifest['layers']), 1)
        self.assertEqual(manifest['layers'][0]['mediaType'], a.LAYER)
        self.assertNotIn('annotations', manifest['layers'][0])
        self.assertEqual(manifest['config']['data'], 'e30=')
        state = self.state()
        self.assertEqual(len({state[k] for k in ['manifest_digest', 'tarball_digest', 'sbom_digest']}), 3)

    def test_sbom_stable_across_clock_and_scan_location(self):
        first = self.inventory()
        self.syft['creationInfo']['created'] = 'tomorrow'
        self.syft['packages'][0]['name'] = '/different'
        self.syft['packages'][0]['SPDXID'] = 'SPDXRef-DocumentRoot-Directory-/different'
        self.syft['relationships'][0]['spdxElementId'] = self.syft['packages'][0]['SPDXID']
        self.assertEqual(first, self.inventory())

    def test_sbom_covers_every_file_and_declared_dependencies(self):
        sbom = json.loads(self.inventory())
        self.assertEqual({f['fileName'] for f in sbom['files']}, {'./metadata.json', './run'})
        self.assertIn('>= 2.0', sbom['packages'][0]['comment'])
        run = next(f for f in sbom['files'] if f['fileName'] == './run')
        self.assertEqual(run['checksums'][0]['checksumValue'], a.digest((self.root / 'run').read_bytes())[7:])
        identifiers = {sbom['SPDXID']} | {p['SPDXID'] for p in sbom['packages']} | {f['SPDXID'] for f in sbom['files']}
        for relation in sbom['relationships']:
            self.assertIn(relation['spdxElementId'], identifiers)
            self.assertIn(relation['relatedSpdxElement'], identifiers)

    def test_release_commit_is_in_provenance(self):
        predicate = json.loads((self.work / 'provenance.json').read_text())
        dependencies = predicate['buildDefinition']['resolvedDependencies']
        self.assertEqual(dependencies[0]['digest']['gitCommit'], self.args.commit)

    def test_existing_different_tag_is_never_overwritten(self):
        with patch.object(a, 'resolve', return_value='sha256:' + 'c' * 64), patch.object(a, 'run') as run:
            with self.assertRaises(ValueError):
                a.push(self.args)
            run.assert_not_called()

    def test_matching_tag_can_be_recovered(self):
        with patch.object(a, 'resolve', return_value=self.state()['manifest_digest']):
            a.check_tag(self.state())

    def test_auth_failure_is_not_interpreted_as_missing_tag(self):
        error = subprocess.CompletedProcess([], 1, '', 'unauthorized: access denied')
        with patch.object(a.subprocess, 'run', return_value=error):
            with self.assertRaises(RuntimeError):
                a.resolve('registry/example:1')

    def test_substituted_sbom_and_subject_rejected(self):
        state = self.state()
        sbom = json.loads(self.inventory())
        statement = {'subject': [{'name': state['repository'], 'digest': {'sha256': state['manifest_digest'][7:]}}],
                     'predicateType': a.SPDX_PREDICATE, 'predicate': sbom}
        a.validate_statement(statement, state, a.SPDX_PREDICATE, sbom)
        wrong = copy.deepcopy(statement)
        wrong['subject'][0]['digest']['sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            a.validate_statement(wrong, state, a.SPDX_PREDICATE, sbom)
        wrong = copy.deepcopy(sbom)
        wrong['name'] = 'substituted'
        with self.assertRaises(ValueError):
            a.validate_statement(statement, state, a.SPDX_PREDICATE, wrong)

    def test_recovery_reuses_only_verified_evidence(self):
        with patch.object(a, 'verify_evidence') as verify, patch.object(a, 'output') as output:
            verify.side_effect = [None, ValueError('missing'), None]
            a.evidence(self.args)
            self.assertEqual(output.call_args_list[0].kwargs, {'signature': 'true'})
            self.assertEqual(output.call_args_list[1].kwargs, {'provenance': 'false'})
            self.assertEqual(output.call_args_list[2].kwargs, {'sbom': 'true'})

    def test_verifier_enforces_expected_identity(self):
        with patch.object(a, 'run') as run:
            a.verify_evidence(self.state(), self.work, 'signature')
            args = run.call_args.args
            self.assertIn('https://github.com/' + self.args.workflow_ref, args)
            self.assertIn('https://token.actions.githubusercontent.com', args)
            self.assertIn(self.state()['repository'] + '@' + self.state()['manifest_digest'], args)


if __name__ == '__main__':
    unittest.main()
