"""Malformed boot packages and physical range conflicts must fail before any device action."""
import importlib.util
import io
from pathlib import Path
import struct
import tarfile
import unittest

spec=importlib.util.spec_from_file_location('boot',Path(__file__).resolve().parents[1]/'tools/verify/boot.py')
boot=importlib.util.module_from_spec(spec);spec.loader.exec_module(boot)


def fixture():
    data=bytearray(8192)
    data[:8]=b'ANDROID!';struct.pack_into('<4I',data,8,64,0,0,1584);struct.pack_into('<I',data,40,4)
    data[4096+56:4096+60]=b'ARM\x64';struct.pack_into('<Q',data,4096+16,64)
    return bytes(data)+boot.FOOTER


class ImageTests(unittest.TestCase):
    def test_loader_format_pass_never_claims_xnu_or_hardware(self):
        report=boot.inspect(fixture())
        self.assertFalse(report['xnu_payload_verified']);self.assertFalse(report['hardware_boot_verified'])

    def test_truncation_size_mismatch_footer_and_ramdisk_are_rejected(self):
        original=fixture()
        bad=[original[:100],original[:-1],original+b'junk']
        for offset,value in [(8,65),(12,4096),(40,3),(1580,1),(4096+16,63)]:
            b=bytearray(original);struct.pack_into('<I',b,offset,value);bad.append(bytes(b))
        b=bytearray(original);b[5000]=1;bad.append(bytes(b))
        for data in bad:
            with self.subTest(length=len(data)),self.assertRaises(ValueError):boot.inspect(data)

    def test_tar_rejects_extra_members_symlinks_and_different_bytes(self):
        for name,content,symlink in [('vbmeta.img',b'x',False),('boot.img',b'wrong',False),('boot.img',b'',True)]:
            out=io.BytesIO()
            with tarfile.open(fileobj=out,mode='w') as archive:
                member=tarfile.TarInfo(name);member.size=len(content)
                if symlink:member.type=tarfile.SYMTYPE;member.linkname='/tmp/other'
                archive.addfile(member,io.BytesIO(content))
            with self.assertRaises(ValueError):boot.inspect_tar(out.getvalue(),fixture())

    def test_overlap_reserved_holes_and_integer_overflow(self):
        self.assertEqual(boot.spans([(4096,4096),(12288,4096)],[(8192,4096)]),[(4096,4096),(12288,4096)])
        for ranges,reserved in [([(1,8),(8,2)],[]),([(0,8192)],[(4096,1)]),([(2**64-1,2)],[]),([(0,0)],[])]:
            with self.subTest(ranges=ranges),self.assertRaises(ValueError):boot.spans(ranges,reserved)

    def test_entry_rejects_unmapped_non_executable_and_zero_fill_ranges(self):
        segments=[(0x1000,0x1000,0x100,True),(0x3000,0x1000,0x1000,False)]
        self.assertEqual(boot.entrypoint(0x1000,segments),0x1000)
        for address in [0,0x1100,0x2000,0x3000,0x4000]:
            with self.subTest(address=address),self.assertRaises(ValueError):boot.entrypoint(address,segments)


if __name__=='__main__':unittest.main()
