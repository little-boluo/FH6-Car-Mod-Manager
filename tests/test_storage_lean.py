import os
import re
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from cache_storage import prune_cache, cleanup_stale_jobs, rotate_error_log, OWNER_FILE, OWNER_VALUE
import test_thumbnails as thumbnail_fixtures


class CacheStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()

    def png(self, digit, size, accessed):
        p=self.root/(digit*64+'.png');p.write_bytes(b'x'*size);os.utime(p,(accessed,accessed));return p

    def test_quota_removes_least_recently_used_only(self):
        old=self.png('a',60,100);new=self.png('b',60,200)
        user=self.root/'my-picture.png';user.write_bytes(b'user image')
        prune_cache(self.root,max_bytes=70,max_age=1000,now=300)
        self.assertFalse(old.exists());self.assertTrue(new.exists());self.assertTrue(user.exists())

    def test_protected_current_preview_and_recent_files_survive_age_cleanup(self):
        old=self.png('a',50,100);protected=self.png('b',50,100);new=self.png('c',50,290)
        prune_cache(self.root,protected=[protected],max_bytes=1000,max_age=50,now=300)
        self.assertFalse(old.exists());self.assertTrue(protected.exists());self.assertTrue(new.exists())

    def test_empty_cache_and_missing_files_are_safe(self):
        prune_cache(self.root,max_bytes=0);cleanup_stale_jobs(self.root);rotate_error_log(self.root)
        self.assertEqual(list(self.root.iterdir()),[])

    def test_only_stale_owned_job_directories_are_removed(self):
        for name in ['render-abcdefgh','render-ijklmnop','render-qrstuvwx','unrelated']:
            (self.root/name).mkdir();(self.root/name/'mod.zip').write_bytes(b'keep')
        old=self.root/'render-abcdefgh';recent=self.root/'render-ijklmnop'
        for p,ts in [(old,0),(recent,100000)]:
            marker=p/OWNER_FILE;marker.write_text(OWNER_VALUE);os.utime(marker,(ts,ts))
        cleanup_stale_jobs(self.root,now=100001)
        self.assertFalse(old.exists());self.assertTrue(recent.exists())
        self.assertTrue((self.root/'render-qrstuvwx'/'mod.zip').exists())
        self.assertTrue((self.root/'unrelated'/'mod.zip').exists())

    def test_wrong_ownership_marker_is_not_deleted(self):
        p=self.root/'render-abcdefgh';p.mkdir();m=p/OWNER_FILE;m.write_text('not our folder');os.utime(m,(0,0))
        cleanup_stale_jobs(self.root,now=100000);self.assertTrue(p.exists())

    def test_logs_keep_one_previous_copy(self):
        log=self.root/'errors.log';log.write_bytes(b'x'*(2*1024*1024+1));rotate_error_log(self.root)
        self.assertFalse(log.exists());self.assertTrue((self.root/'errors.previous.log').exists())

    def test_symlink_outside_cache_is_not_followed(self):
        target=self.root/'outside';target.mkdir();image=target/('a'*64+'.png');image.write_bytes(b'keep')
        link=self.root/('b'*64+'.png')
        try:link.symlink_to(image)
        except OSError:self.skipTest('Symlink creation unavailable on this Windows account')
        prune_cache(self.root,max_bytes=0,max_age=0,now=10**12)
        self.assertEqual(image.read_bytes(),b'keep');self.assertTrue(link.is_symlink())


class CacheHitTests(unittest.TestCase):
    setUp = thumbnail_fixtures.ThumbnailTests.setUp
    req = thumbnail_fixtures.ThumbnailTests.req
    fake_renderer = thumbnail_fixtures.ThumbnailTests.fake_renderer
    def test_hit_does_not_create_full_archive_copies(self):
        with patch('thumbnails.subprocess.Popen',side_effect=self.fake_renderer):
            self.service._generate(self.req())
        with patch('thumbnails.tempfile.TemporaryDirectory',side_effect=AssertionError('cache hit wrote temp ZIP')):
            path,_=self.service._generate(self.req())
            self.assertTrue(path.is_file())

class LeanBuildTests(unittest.TestCase):
    def test_explicit_project_excludes_shell_docs_and_missing_files(self):
        project=Path(__file__).resolve().parents[1]/'vendor/ForzaTechStudio/ForzaTechStudio/FH6ThumbnailRenderer.csproj'
        root=ET.parse(project).getroot()
        for item in root.findall('.//Compile')+root.findall('.//Page'):
            self.assertTrue((project.parent/Path(item.attrib['Include'].replace('\\','/'))).is_file(),item.attrib)
        pages=[p.attrib['Include'] for p in root.findall('.//Page')]
        self.assertIn('Views\\ViewportPage.xaml',pages)
        self.assertNotIn('Views\\ShellPage.xaml',pages)
        self.assertNotIn('Views\\DocumentationPage.xaml',pages)
        packages=[p.attrib['Include'] for p in root.findall('.//PackageReference')]
        self.assertNotIn('CommunityToolkit.WinUI.UI.Controls.Markdown',packages)
        self.assertIn('Microsoft.Data.Sqlite',packages)
        self.assertIn('HelixToolkit.WinUI',packages)
        self.assertEqual(root.find('.//EnableDefaultCompileItems').text,'false')
        self.assertEqual(root.find('.//PublishTrimmed').text,'false')
        self.assertEqual(root.find('.//EnableMsixTooling').text,'true')
        self.assertEqual(root.find('.//EnableCoreMrtTooling').text,'true')
        self.assertEqual(root.find('.//ProjectPriFileName').text,'resources.pri')
        for item in root.findall('.//Page')+root.findall('.//ApplicationDefinition'):
            self.assertEqual(item.find('Generator').text,'MSBuild:Compile')
            self.assertEqual(item.find('XamlRuntime').text,'WinUI')

    def test_local_xaml_controls_and_generated_code_are_included(self):
        project=Path(__file__).resolve().parents[1]/'vendor/ForzaTechStudio/ForzaTechStudio/FH6ThumbnailRenderer.csproj'
        root=ET.parse(project).getroot()
        sources=[project.parent/p.attrib['Include'].replace('\\','/') for p in root.findall('.//Compile')]
        pages=[project.parent/p.attrib['Include'].replace('\\','/') for p in root.findall('.//Page')+root.findall('.//ApplicationDefinition')]
        declared=set()
        for source in sources:
            code=source.read_text(encoding='utf-8-sig')
            declared.update(re.findall(r'\bclass\s+(\w+)',code))
            if 'this.InitializeComponent()' in code:
                self.assertIn(source.with_suffix(''),pages,str(source))
        for page in pages:
            for node in ET.parse(page).iter():
                if node.tag.startswith('{using:ForzaTechStudio.'):
                    name=node.tag.split('}',1)[1].split('.',1)[0]
                    self.assertIn(name,declared,f'{page}: {name}')


if __name__=='__main__' :unittest.main()
