import os
import shutil

from cStringIO import StringIO
from tempfile import mkstemp
from tests import TestCase, add
from mutagen.mp4 import (MP4, Atom, Atoms, MP4Tags, MP4Info, delete, MP4Cover,
    MP4MetadataError)
try: from os.path import devnull
except ImportError: devnull = "/dev/null"

class TAtom(TestCase):
    uses_mmap = False

    def test_no_children(self):
        fileobj = StringIO("\x00\x00\x00\x08atom")
        atom = Atom(fileobj)
        self.failUnlessRaises(KeyError, atom.__getitem__, "test")

    def test_length_1(self):
        fileobj = StringIO("\x00\x00\x00\x01atom" + "\x00" * 8)
        self.failUnlessRaises(IOError, Atom, fileobj)

    def test_render_too_big(self):
        class TooBig(str):
            def __len__(self):
                return 1L << 32
        data = TooBig("test")
        try: len(data)
        except OverflowError:
            # Py_ssize_t is still only 32 bits on this system.
            self.failUnlessRaises(OverflowError, Atom.render, "data", data)
        else:
            data = Atom.render("data", data)
            self.failUnlessEqual(len(data), 4 + 4 + 8 + 4)

    def test_length_0(self):
        fileobj = StringIO("\x00\x00\x00\x00atom")
        Atom(fileobj)
        self.failUnlessEqual(fileobj.tell(), 8)
add(TAtom)

class TAtoms(TestCase):
    uses_mmap = False
    filename = os.path.join("tests", "data", "has-tags.m4a")

    def setUp(self):
        self.atoms = Atoms(file(self.filename, "rb"))

    def test___contains__(self):
        self.failUnless(self.atoms["moov"])
        self.failUnless(self.atoms["moov.udta"])
        self.failUnlessRaises(KeyError, self.atoms.__getitem__, "whee")

    def test_name(self):
        self.failUnlessEqual(self.atoms.atoms[0].name, "ftyp")

    def test_children(self):
        self.failUnless(self.atoms.atoms[2].children)

    def test_no_children(self):
        self.failUnless(self.atoms.atoms[0].children is None)

    def test_repr(self):
        repr(self.atoms)
add(TAtoms)

class TMP4Info(TestCase):
    uses_mmap = False

    def test_no_soun(self):
        self.failUnlessRaises(
            IOError, self.test_mdhd_version_1, "no so und data here")

    def test_mdhd_version_1(self, soun="soun"):
        mdhd = Atom.render("mdhd", ("\x01\x00\x00\x00" + "\x00" * 16 +
                                    "\x00\x00\x00\x02" + # 2 Hz
                                    "\x00\x00\x00\x00\x00\x00\x00\x10"))
        hdlr = Atom.render("hdlr", soun)
        mdia = Atom.render("mdia", mdhd + hdlr)
        trak = Atom.render("trak", mdia)
        moov = Atom.render("moov", trak)
        fileobj = StringIO(moov)
        atoms = Atoms(fileobj)
        info = MP4Info(atoms, fileobj)
        self.failUnlessEqual(info.length, 8)
add(TMP4Info)

class TMP4Tags(TestCase):
    uses_mmap = False

    def wrap_ilst(self, data):
        ilst = Atom.render("ilst", data)
        meta = Atom.render("meta", "\x00" * 4 + ilst)
        data = Atom.render("moov", Atom.render("udta", meta))
        fileobj = StringIO(data)
        return MP4Tags(Atoms(fileobj), fileobj)
        
    def test_bad_freeform(self):
        mean = Atom.render("mean", "net.sacredchao.Mutagen")
        name = Atom.render("name", "empty test key")
        bad_freeform = Atom.render("----", "\x00" * 4 + mean + name)
        self.failIf(self.wrap_ilst(bad_freeform))

    def test_genre(self):
        data = Atom.render("data", "\x00" * 8 + "\x00\x01")
        genre = Atom.render("gnre", data)
        tags = self.wrap_ilst(genre)
        self.failIf("gnre" in tags)
        self.failUnlessEqual(tags.get("\xa9gen"), "Blues")

    def test_empty_cpil(self):
        cpil = Atom.render("cpil", Atom.render("data", "\x00" * 8))
        tags = self.wrap_ilst(cpil)
        self.failUnless("cpil" in tags)
        self.failIf(tags["cpil"])

    def test_genre_too_big(self):
        data = Atom.render("data", "\x00" * 8 + "\x01\x00")
        genre = Atom.render("gnre", data)
        tags = self.wrap_ilst(genre)
        self.failIf("gnre" in tags)
        self.failIf("\xa9gen" in tags)

    def test_strips_unknown_types(self):
        data = Atom.render("data", "\x00" * 8 + "whee")
        foob = Atom.render("foob", data)
        tags = self.wrap_ilst(foob)
        self.failIf(tags)

    def test_bad_covr(self):
        data = Atom.render("foob", "\x00\x00\x00\x0E" + "\x00" * 4 + "whee")
        covr = Atom.render("covr", data)
        self.failUnlessRaises(MP4MetadataError, self.wrap_ilst, covr)

    def test_render_bool(self):
        self.failUnlessEqual(MP4Tags()._MP4Tags__render_bool('pgap', True),
                             "\x00\x00\x00\x19pgap\x00\x00\x00\x11data"
                             "\x00\x00\x00\x15\x00\x00\x00\x00\x01")
        self.failUnlessEqual(MP4Tags()._MP4Tags__render_bool('pgap', False),
                             "\x00\x00\x00\x19pgap\x00\x00\x00\x11data"
                             "\x00\x00\x00\x15\x00\x00\x00\x00\x00")

    def test_render_text(self):
        self.failUnlessEqual(
             MP4Tags()._MP4Tags__render_text('purl', 'http://foo/bar.xml', 0),
             "\x00\x00\x00*purl\x00\x00\x00\"data\x00\x00\x00\x00\x00\x00"
             "\x00\x00http://foo/bar.xml")
        self.failUnlessEqual(
             MP4Tags()._MP4Tags__render_text('aART', 'Album Artist'),
             "\x00\x00\x00$aART\x00\x00\x00\x1cdata\x00\x00\x00\x01\x00\x00"
             "\x00\x00Album Artist")

add(TMP4Tags)

class TMP4(TestCase):
    def setUp(self):
        fd, self.filename = mkstemp(suffix='m4a')
        os.close(fd)
        shutil.copy(self.original, self.filename)
        self.audio = MP4(self.filename)

    def faad(self):
        if not have_faad: return
        value = os.system(
            "faad -w %s > %s 2> %s" % (self.filename,
                devnull, devnull))
        self.failIf(value and value != NOTFOUND)

    def test_bitrate(self):
        self.failUnlessEqual(self.audio.info.bitrate, 2914)

    def test_length(self):
        self.failUnlessAlmostEqual(3.7, self.audio.info.length, 1)

    def set_key(self, key, value):
        self.audio[key] = value
        self.audio.save()
        audio = MP4(self.audio.filename)
        self.failUnless(key in audio)
        self.failUnlessEqual(audio[key], value)
        self.faad()

    def test_save_text(self):
        self.set_key('\xa9nam', u"Some test name")

    def test_freeform(self):
        self.set_key('----:net.sacredchao.Mutagen:test key', "whee")

    def test_tracknumber(self):
        self.set_key('trkn', (1, 10))

    def test_disk(self):
        self.set_key('disk', (18, 0))

    def test_tracknumber_too_small(self):
        self.failUnlessRaises(ValueError, self.set_key, 'trkn', (-1, 0))
        self.failUnlessRaises(ValueError, self.set_key, 'trkn', (2**18, 1))

    def test_disk_too_small(self):
        self.failUnlessRaises(ValueError, self.set_key, 'disk', (-1, 0))
        self.failUnlessRaises(ValueError, self.set_key, 'disk', (2**18, 1))

    def test_tracknumber_wrong_size(self):
        self.failUnlessRaises(ValueError, self.set_key, 'trkn', (1,))
        self.failUnlessRaises(ValueError, self.set_key, 'trkn', (1, 2, 3,))

    def test_disk_wrong_size(self):
        self.failUnlessRaises(ValueError, self.set_key, 'disk', (1,))
        self.failUnlessRaises(ValueError, self.set_key, 'disk', (1, 2, 3,))

    def test_tempo(self):
        self.set_key('tmpo', 150)

    def test_tempo_invalid(self):
        self.failUnlessRaises(ValueError, self.set_key, 'tmpo', 100000)

    def test_compilation(self):
        self.set_key('cpil', True)

    def test_compilation_false(self):
        self.set_key('cpil', False)

    def test_gapless(self):
        self.set_key('pgap', True)

    def test_gapless_false(self):
        self.set_key('pgap', False)

    def test_podcast(self):
        self.set_key('pcst', True)

    def test_podcast_false(self):
        self.set_key('pcst', False)

    def test_cover(self):
        self.set_key('covr', ['woooo'])

    def test_cover_png(self):
        self.set_key('covr', [
            MP4Cover('woooo', MP4Cover.FORMAT_PNG),
            MP4Cover('hoooo', MP4Cover.FORMAT_JPEG),
        ])

    def test_podcast_url(self):
        self.set_key('purl', 'http://pdl.warnerbros.com/wbie/justiceleagueheroes/audio/JLH_EA.xml')

    def test_pprint(self):
        self.audio.pprint()

    def test_pprint_binary(self):
        self.audio["covr"] = "\x00\xa9\garbage"
        self.audio.pprint()

    def test_delete(self):
        self.audio.delete()
        audio = MP4(self.audio.filename)
        self.failIf(audio.tags)
        self.faad()

    def test_module_delete(self):
        delete(self.filename)
        audio = MP4(self.audio.filename)
        self.failIf(audio.tags)
        self.faad()

    def test_reads_unknown_text(self):
        self.set_key("foob", u"A test")

    def tearDown(self):
        os.unlink(self.filename)

class TMP4HasTags(TMP4):
    original = os.path.join("tests", "data", "has-tags.m4a")

    def test_save_simple(self):
        self.audio.save()
        self.faad()

    def test_shrink(self):
        map(self.audio.__delitem__, self.audio.keys())
        self.audio.save()
        audio = MP4(self.audio.filename)
        self.failIf(self.audio.tags)

    def test_has_tags(self):
        self.failUnless(self.audio.tags)

    def test_has_covr(self):
        self.failUnless('covr' in self.audio.tags)
        covr = self.audio.tags['covr']
        self.failUnlessEqual(len(covr), 2)
        self.failUnlessEqual(covr[0].format, MP4Cover.FORMAT_PNG)
        self.failUnlessEqual(covr[1].format, MP4Cover.FORMAT_JPEG)

    def test_not_my_file(self):
        self.failUnlessRaises(
            IOError, MP4, os.path.join("tests", "data", "empty.ogg"))

add(TMP4HasTags)

class TMP4NoTags(TMP4):
    original = os.path.join("tests", "data", "no-tags.m4a")

    def test_no_tags(self):
        self.failUnless(self.audio.tags is None)

add(TMP4NoTags)

NOTFOUND = os.system("tools/notarealprogram 2> %s" % devnull)

have_faad = True
if os.system("faad 2> %s > %s" % (devnull, devnull)) == NOTFOUND:
    have_faad = False
    print "WARNING: Skipping FAAD reference tests."
