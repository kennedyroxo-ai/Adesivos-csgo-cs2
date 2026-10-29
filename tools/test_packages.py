import io,json,struct,tempfile,unittest,zipfile,sys
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import package_stickers
from vtf_png import decode,png

def vtf(color):
    b=bytearray(80);b[:4]=b'VTF\0'
    struct.pack_into('<III',b,4,7,2,80);struct.pack_into('<HH',b,16,2,2)
    struct.pack_into('<H',b,24,1);struct.pack_into('<I',b,52,0);b[56]=1
    struct.pack_into('<I',b,57,0xffffffff);struct.pack_into('<H',b,63,1)
    return bytes(b)+bytes(color)*4

class PackagesTest(unittest.TestCase):
    def test_known_source_filename_repair_preserves_both_original_and_alias_bytes(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)/'src';dest=Path(t)/'out';p=root/'stickers/cluj2015';p.mkdir(parents=True)
            payload=vtf((255,200,10,255))
            (p/'ninjasinpyjamas.vtf').write_bytes(payload)
            (p/'ninjasinpyjamas_foil.vmt').write_text('WeaponDecal { $basetexture stickers/cluj2015/sig_ninjasinpyjamas }')
            with patch.object(sys,'argv',['pack',str(root),'--out',str(dest)]):package_stickers.main()
            item=json.loads((dest/'catalog.json').read_text())['items'][0]
            with zipfile.ZipFile(io.BytesIO((dest/Path(item['url']).name).read_bytes())) as z:
                self.assertEqual(z.read('stickers/cluj2015/sig_ninjasinpyjamas.vtf'),payload)
                self.assertEqual(z.read('stickers/cluj2015/ninjasinpyjamas.vtf'),payload)
                self.assertTrue(json.loads(z.read('package.json'))['filename_aliases'])

    def test_vtf_keeps_alpha_and_channels(self):
        im,_=decode(vtf((20,40,60,80)))
        self.assertEqual(im.getpixel((0,0)),(20,40,60,80))
        with self.assertRaises(ValueError):decode(vtf((1,2,3,4))[:-2])
        im=Image.open(io.BytesIO(png(vtf((200,100,50,80)),tint=(128,255,0))[0]))
        self.assertEqual(im.getpixel((0,0)),(100,100,0,80))

    def test_dependency_resolution_bundle_ranges_and_failures(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)/'src';dest=Path(t)/'out';p=root/'stickers/test';p.mkdir(parents=True)
            default=root/'stickers/default';default.mkdir()
            (default/'holowarp_default.vtf').write_bytes(vtf((255,0,128,255)))
            (p/'base.vtf').write_bytes(vtf((255,255,255,128)))
            (p/'mask.vtf').write_bytes(vtf((255,100,80,255)))
            (p/'first.vmt').write_text('WeaponDecal { "$basetexture" "models\\weapons\\customization\\stickers\\test\\base" "$holomask" "stickers/test/mask" "$holospectrum" "stickers/default/holowarp_default" }')
            (p/'plain.vmt').write_text('WeaponDecal { $basetexture stickers/test/base }')
            (p/'missing.vmt').write_text('WeaponDecal { $basetexture stickers/test/missing }')
            with patch.object(sys,'argv',['pack',str(root),'--out',str(dest)]):package_stickers.main()
            c=json.loads((dest/'catalog.json').read_text());r=json.loads((dest/'package-report.json').read_text())
            self.assertEqual((r['ready'],r['failed']),(2,1))
            for item in c['items']:
                data=(dest/Path(item['url']).name).read_bytes()[item['offset']:item['offset']+item['size']]
                self.assertEqual(package_stickers.digest(data),item['sha256'])
                with zipfile.ZipFile(io.BytesIO(data)) as z:
                    self.assertIn('image.png',z.namelist())
                    self.assertIn('stickers/test/base.vtf',z.namelist())
                    im=Image.open(z.open('image.png'));self.assertEqual(im.getpixel((0,0)),(255,255,255,128))
                    if item['holo']:
                        self.assertEqual(z.read('spectrum.vtf'),(default/'holowarp_default.vtf').read_bytes())
                        self.assertIn('mask.png',z.namelist())
            self.assertTrue(c['items'][0]['holo'])
if __name__=='__main__':unittest.main()
