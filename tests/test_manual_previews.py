"""Manual images stay isolated by mod identity and survive status renames."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch
from PIL import Image
from app import Application
from thumbnails import ThumbnailService, Request, stamp
from thumbnail_failures import FAILURE_STATUS
from cache_storage import prune_cache
from manual_previews import prepare_preview, SIZE


class ManualPreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.a = self.home/'A.zip'; self.a.write_bytes(b'first mod')
        self.b = self.home/'A__fh6mm_v1.zipdisabled'; self.b.write_bytes(b'first mod')
        self.picture = self.home/'photo.jpg'
        Image.new('RGB',(800,400),'red').save(self.picture)
        self.service = ThumbnailService(self.home, running=lambda:False)
        self.addCleanup(self.service.close)

    def test_import_preserves_sources_and_isolates_identical_mod_copies(self):
        before = self.a.read_bytes(), self.picture.read_bytes()
        target = self.service.import_manual(self.a,self.picture)
        self.assertEqual(self.service.request(self.a),(target,'手动缩略图'))
        self.assertIsNone(self.service.request(self.b)[0])
        self.assertEqual((self.a.read_bytes(),self.picture.read_bytes()),before)
        with Image.open(target) as im:
            self.assertEqual(im.size,SIZE); self.assertEqual(im.format,'PNG')
            self.assertEqual(im.getpixel((0,0)),(19,25,37))
            self.assertGreater(im.getpixel((342,192))[0],240)

    def test_restart_and_variant_rename_preserve_manual_image(self):
        target = self.service.import_manual(self.a,self.picture)
        renamed = self.home/'A__fh6mm_v2.zipdisabled';self.a.rename(renamed)
        self.service.close()
        again = ThumbnailService(self.home,running=lambda:False);self.addCleanup(again.close)
        self.assertEqual(again.request(renamed)[0],target)
        self.assertTrue(again.tasks.empty())

    def test_custom_image_wins_over_failure_missing_renderer_and_original(self):
        self.service.failures.remember(stamp(self.a),'a'*64)
        self.assertEqual(self.service.request(self.a)[1],FAILURE_STATUS)
        target=self.service.import_manual(self.a,self.picture)
        self.assertEqual(self.service.request(self.a,self.home/'missing-original.zip')[0],target)
        self.assertTrue(self.service.tasks.empty())

    def test_rebuild_removes_only_selected_manual_image(self):
        a=self.service.import_manual(self.a,self.picture)
        b=self.service.import_manual(self.b,self.picture)
        self.service.invalidate(self.a)
        self.assertFalse(a.exists());self.assertTrue(b.exists())
        self.assertIsNone(self.service.request(self.a)[0])
        self.assertEqual(self.service.request(self.b)[0],b)

    def test_cache_pruning_does_not_delete_user_image(self):
        target=self.service.import_manual(self.a,self.picture)
        prune_cache(self.service.cache,max_bytes=0,max_age=0,now=10**12)
        self.assertTrue(target.is_file())

    def test_bad_image_preserves_previous_custom_picture(self):
        target=self.service.import_manual(self.a,self.picture);before=target.read_bytes()
        self.picture.write_bytes(b'not an image')
        with self.assertRaises(ValueError):self.service.import_manual(self.a,self.picture)
        self.assertEqual(target.read_bytes(),before)
        self.assertFalse(list(self.service.manual.glob('*.tmp')))

    def test_mod_changed_during_dialog_cannot_receive_image(self):
        before=stamp(self.a);self.a.write_bytes(b'changed mod content')
        with self.assertRaises(OSError):self.service.import_manual(self.a,self.picture,before)
        self.assertFalse(list(self.service.manual.glob('*.png')))

    def test_game_start_during_conversion_keeps_old_image(self):
        target=self.service.import_manual(self.a,self.picture);before=target.read_bytes()
        self.service.running=Mock(side_effect=[False,True])
        with self.assertRaises(OSError):self.service.import_manual(self.a,self.picture)
        self.assertEqual(target.read_bytes(),before)
        self.assertFalse(list(self.service.manual.glob('*.tmp')))

    def test_stale_renderer_result_cannot_override_custom_image(self):
        signature=self.service.signature(self.a)
        req=Request(self.a,None,None,signature,0)
        self.service.pending.add(signature)
        target=self.service.import_manual(self.a,self.picture)
        self.service.results.put((req,(self.home/'old.png','已生成')))
        self.service.drain()
        self.assertNotIn(signature,self.service.completed)
        self.assertEqual(self.service.request(self.a)[0],target)

    def test_changed_mod_content_does_not_reuse_manual_image(self):
        self.service.import_manual(self.a,self.picture)
        self.a.write_bytes(b'new mod with different size')
        self.assertIsNone(self.service.request(self.a)[0])

    def test_all_supported_formats_and_transparency(self):
        for fmt,ext in [('PNG','png'),('JPEG','jpg'),('WEBP','webp'),('BMP','bmp')]:
            with self.subTest(fmt=fmt):
                path=self.home/('input.'+ext)
                Image.new('RGB',(100,200),'blue').save(path,format=fmt)
                output=self.home/'out.png';prepare_preview(path,output)
                with Image.open(output) as im:self.assertEqual(im.size,SIZE)
        transparent=self.home/'alpha.png'
        Image.new('RGBA',(20,20),(255,0,0,0)).save(transparent)
        prepare_preview(transparent,output)
        with Image.open(output) as im:self.assertEqual(im.getpixel((342,192)),(19,25,37))

    def test_exif_orientation_is_applied_and_metadata_stripped(self):
        exif=Image.Exif();exif[274]=6
        Image.new('RGB',(100,200),'red').save(self.picture,exif=exif)
        out=self.home/'out.png';prepare_preview(self.picture,out)
        with Image.open(out) as im:
            self.assertEqual(im.getpixel((0,0)),(19,25,37))
            self.assertGreater(im.getpixel((30,192))[0],240)
            self.assertFalse(im.getexif())


class ManualPreviewActionTests(unittest.TestCase):
    def app(self, folder):
        app=Application.__new__(Application)
        app.manager=SimpleNamespace(folder=Path(folder));app.rows={'CAR.zip':object()}
        (Path(folder)/'CAR.zip').write_bytes(b'mod')
        app.tree=Mock();app.tree.selection.return_value=('CAR.zip',)
        app.can_edit=Mock(return_value=True);app.root=Mock();app.status=Mock()
        app.run=Mock();app.error=Mock();app.thumbnails=Mock()
        return app

    def test_cancel_and_game_lock_after_dialog_do_not_schedule_import(self):
        with tempfile.TemporaryDirectory() as folder:
            app=self.app(folder)
            with patch('app.filedialog.askopenfilename',return_value=''):
                app.import_thumbnail()
            app.run.assert_not_called()
            app.can_edit.side_effect=[True,False]
            with patch('app.filedialog.askopenfilename',return_value='photo.png'):
                app.import_thumbnail()
            app.run.assert_not_called()

    def test_selection_captured_before_dialog(self):
        with tempfile.TemporaryDirectory() as folder:
            app=self.app(folder)
            def choose(**kwargs):
                app.tree.selection.return_value=('OTHER.zip',)
                return 'photo.png'
            with patch('app.filedialog.askopenfilename',side_effect=choose):app.import_thumbnail()
            app.run.call_args.args[1]()
            args=app.thumbnails.import_manual.call_args.args
            self.assertEqual(args[0],Path(folder)/'CAR.zip')
            self.assertEqual(args[1],'photo.png')
