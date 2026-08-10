import os
import re
import unittest
import json
import site
import tomllib

class MetadataTest(unittest.TestCase):

    @classmethod
    def get_site_package_folder(cls):
          for f in site.getsitepackages():
            if 'site-packages' in f:
                return f

    @classmethod
    def find_lib_folder(cls, lib_name:str):
        dirs = [f for f in os.listdir(cls.get_site_package_folder()) if f.startswith(lib_name.replace('-', '_')+'-')]
        if len(dirs) == 1:
            return os.path.join(cls.get_site_package_folder(), dirs[0])
        return None

    @classmethod
    def get_installed_lib_version(cls, lib_name:str):

        dir_name = cls.find_lib_folder(lib_name)
        if dir_name:
            metadata_file = os.path.join(dir_name, 'METADATA')
            with open(metadata_file, 'r') as f:
                for line in f.readlines():
                    if line.startswith('Version: '):
                        return line.replace('Version: ', '').strip()
            return None
        return None

    @classmethod
    def get_version_of_installed_eltako14bus(cls):
        return cls.get_installed_lib_version('eltako14bus')

    @classmethod
    def get_manifest(cls):
        manifest_filename = os.path.join(os.getcwd(), 'custom_components', 'eltako', 'manifest.json')
        with open(manifest_filename, 'r') as f:
            return json.loads( f.read() )

    @classmethod
    def get_version_of_required_eltako14bus(cls):
        manifest = cls.get_manifest()

        for r in manifest['requirements']:
            if r.startswith('eltako14bus'):
                return r.split('==')[1].strip()
        return None

    @classmethod
    def get_version_of_eltako_integration(cls):
        return cls.get_manifest()['version']

    # ------------------------------------------------------- pip package (see pyproject.toml)

    @classmethod
    def get_pyproject(cls):
        with open(os.path.join(os.getcwd(), 'pyproject.toml'), 'rb') as f:
            return tomllib.load(f)

    @classmethod
    def get_version_of_standalone_package(cls):
        """`__version__` of eltako_standalone - read, not imported: importing the package in
        the process of the integration tests would mix it with the real homeassistant."""
        filename = os.path.join(os.getcwd(), 'eltako_standalone', '__init__.py')
        with open(filename, 'r', encoding="utf-8") as f:
            return re.search(r'^__version__ = "([^"]+)"', f.read(), re.M).group(1)

    @classmethod
    def get_requirements_standalone(cls):
        filename = os.path.join(os.getcwd(), 'eltako_standalone', 'requirements-standalone.txt')
        with open(filename, 'r', encoding="utf-8") as f:
            return [line.strip() for line in f
                    if line.strip() and not line.strip().startswith('#')]


    def test_check_all_installed_dependencies(self):
        manifest = self.get_manifest()

        for r in manifest['requirements']:
            if '==' in r:
                lib_name = r.split('==')[0].strip()
                required_version  = r.split('==')[1].strip()
                installed_version = self.get_installed_lib_version(lib_name)

                # if this test fails install specified libraries in manifest.json
                self.assertEqual(required_version, installed_version)


    def test_check_manifest_and_requirements_match(self):
        manifest = self.get_manifest()

        requirements_txt_fn = os.path.join(os.getcwd(), 'requirements.txt')
        with open(requirements_txt_fn, 'r', encoding="utf-8") as f:
            requirements_txt = f.read()

        # every requirement of the integration must be listed in requirements.txt as well
        for r in manifest['requirements']:
            self.assertTrue(r in requirements_txt, msg=f"{r} not in requirements.txt")


    def test_eltako14bus_required_and_installed_is_the_same(self):
        installed = self.get_version_of_installed_eltako14bus()
        required = self.get_version_of_required_eltako14bus()

        self.assertIsNotNone(installed)
        self.assertIsNotNone(required)
        self.assertEqual(installed, required)

    def test_standalone_package_is_named_and_started_as_documented(self):
        """The distribution name and the console scripts are what every readme, the
        documentation and the build pipeline tell people to type."""
        project = self.get_pyproject()['project']

        self.assertEqual('eltako-enocean-tool', project['name'])
        # `eet` is short enough to type, the long one is unmistakable - /usr/bin/eet exists
        # elsewhere (EFL), so the documentation must not depend on the short name alone
        self.assertEqual({'eet': 'eltako_standalone.cli:main',
                          'eltako-enocean-tool': 'eltako_standalone.cli:main'},
                         project['scripts'])

    def test_standalone_package_version_matches_the_integration(self):
        """The pip package (eltako-enocean-tool) ships custom_components/eltako itself, so
        `pip install eltako-enocean-tool==X` must give the integration of version X."""
        self.assertEqual(self.get_version_of_eltako_integration(),
                         self.get_version_of_standalone_package(),
                         msg="bump eltako_standalone/__init__.py together with manifest.json")

        # the version of the wheel is exactly that attribute
        pyproject = self.get_pyproject()
        self.assertEqual({'attr': 'eltako_standalone.__version__'},
                         pyproject['tool']['setuptools']['dynamic']['version'])
        self.assertIn('version', pyproject['project']['dynamic'])

    def test_standalone_package_dependencies_match_the_requirements(self):
        """pyproject.toml is what `pip install` uses, requirements-standalone.txt is what the
        readme tells people to install - they must not drift apart."""
        dependencies = self.get_pyproject()['project']['dependencies']

        self.assertEqual(self.get_requirements_standalone(), dependencies)

        # and the pinned runtime requirements of the integration have to be part of it
        for requirement in self.get_manifest()['requirements']:
            if '==' in requirement:
                self.assertIn(requirement, dependencies,
                              msg=f"{requirement} not in the dependencies of pyproject.toml")

    def test_standalone_package_ships_everything_which_is_read_at_runtime(self):
        """Files the integration opens at runtime are only in the wheel if package-data
        lists them - a new one which is not covered here is missing after `pip install`."""
        package_data = self.get_pyproject()['tool']['setuptools']['package-data']
        patterns = package_data['custom_components.eltako']

        integration_dir = os.path.join(os.getcwd(), 'custom_components', 'eltako')
        for relative in ['manifest.json', 'docs_index.json', 'strings.json', 'services.yaml',
                         os.path.join('translations', 'en.json'),
                         os.path.join('frontend', 'eltako-panel.js'),
                         os.path.join('frontend', 'img', 'eltako-logo.svg')]:
            self.assertTrue(os.path.isfile(os.path.join(integration_dir, relative)),
                            msg=f"{relative} does not exist any more - update pyproject.toml")

        # every page and library of the web ui is covered by the frontend patterns
        self.assertIn('frontend/**/*.js', patterns)
        self.assertIn('frontend/img/*', patterns)

    @classmethod
    def get_release_version(cls):
        """The version without its pre-release marker: 2.2.0rc1 -> 2.2.0.

        A release candidate is a candidate *for* a release, so it describes the changes of
        that release - `changes.md` gets its section when the version is opened, not once per
        candidate. See const.is_prerelease.
        """
        version = cls.get_version_of_eltako_integration()
        return re.match(r'^v?(\d+(?:\.\d+)*)', version).group(1)

    def test_if_changes_are_documented(self):
        changes_filename = os.path.join(os.getcwd(), 'changes.md')
        with open(changes_filename, 'r', encoding="utf-8") as f:
            changes_text = f.read()

        self.assertTrue( f'## Version {self.get_release_version()}' in changes_text )

    def test_a_prerelease_is_recognized_as_one(self):
        """The web ui marks a pre-release as such (eltako/integration_info -> `prerelease`),
        which only works if the version really carries a marker python and HACS both read."""
        from custom_components.eltako.const import is_prerelease

        version = self.get_version_of_eltako_integration()
        # a version with a marker must be a *pre*-release for pip as well: PEP 440 sorts
        # 2.2.0rc1 before 2.2.0, and `pip install` skips it unless it is asked with --pre
        if is_prerelease(version):
            from packaging.version import Version
            self.assertTrue(Version(version).is_prerelease,
                            msg=f"{version} is not a pre-release for pip - use e.g. 2.2.0rc1")
            self.assertNotEqual(version, self.get_release_version())
