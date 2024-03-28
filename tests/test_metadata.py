import os
import sys
import unittest
import json

class MetadataTest(unittest.TestCase):

    def get_installed_lib_version(self, lib_name:str):
        dirs = [f for f in os.listdir(os.path.join(sys.exec_prefix, 'Lib', 'site-packages')) if f.startswith(lib_name.replace('-', '_')+'-')]
        if len(dirs) == 1:
            metadata_file = os.path.join(sys.exec_prefix, 'Lib', 'site-packages', dirs[0], 'METADATA')
            with open(metadata_file, 'r') as f:
                for l in f.readlines():
                    if l.startswith('Version: '):
                        return l.replace('Version: ', '').strip()    
            return None
        return None

    def get_version_of_installed_eltako14bus(self):
        return self.get_installed_lib_version('eltako14bus')

    def get_manifest(self):
        manifest_filename = os.path.join(os.getcwd(), 'custom_components', 'eltako', 'manifest.json')
        with open(manifest_filename, 'r') as f:
            return json.loads( f.read() )

    def get_version_of_required_eltako14bus(self):
        manifest = self.get_manifest()

        for r in manifest['requirements']:
            if r.startswith('eltako14bus'):
                return r.split('==')[1].strip()
        return None
    
    def test_check_all_installed_dependencies(self):
        manifest = self.get_manifest()

        for r in manifest['requirements']:
            if '==' in r:
                lib_name = r.split('==')[0].strip()
                required_version  = r.split('==')[1].strip()
                installed_version = self.get_installed_lib_version(lib_name)

                # if this test fails install specified libraries in manifest.json
                self.assertEqual(required_version, installed_version)


        return None

    def test_eltako14bus_required_and_installed_is_the_same(self):
        installed = self.get_version_of_installed_eltako14bus()
        required = self.get_version_of_required_eltako14bus()

        self.assertIsNotNone(installed)
        self.assertIsNotNone(required)
        self.assertEqual(installed, required)