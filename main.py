"""
    Copyright (c) 2021 Vincent Audric. All Rights Reserved
"""
__license__ = "MIT"
__copyright__ = "Copyright (c) 2021 Vincent Audric"
__author__ = "Vincent Audric"
__version__ = "0.0.1"
__status__ = "at_your_own_risk"

# System
from sys import stderr
from datetime import datetime as DateTime
import struct
from pathlib import Path
from pprint import pprint
import re

# Third-Party
import whatimage
import exifread
from hachoir.stream import input
from hachoir.parser import createParser
from hachoir.metadata.metadata import Metadata
from hachoir.metadata import extractMetadata
from tinytag import TinyTag, TinyTagException

# App

# Refs:
# * https://stackoverflow.com/questions/54395735/how-to-work-with-heic-image-file-types-in-python
# * https://stackoverflow.com/questions/50110800/python-pathlib-make-directories-if-they-don-t-exist
# * https://stackoverflow.com/questions/21355316/getting-metadata-for-mov-video
# Credits to @Stevoisiak

MAKE_CODES = {
    'Apple': 'iOS',
}


def get_mov_timestamps(filename):
    """
        Get the creation and modification date-time from .mov metadata.
        Returns None if a value is not available.
    """
    ATOM_HEADER_SIZE = 8
    # difference between Unix epoch and QuickTime epoch, in seconds
    EPOCH_ADJUSTER = 2082844800

    creation_time = modification_time = None

    # search for moov item
    with open(filename, "rb") as f:
        while True:
            atom_header = f.read(ATOM_HEADER_SIZE)
            # ~ print('atom header:', atom_header)  # debug purposes
            if atom_header[4:8] == b'moov':
                break  # found
            else:
                atom_size = struct.unpack('>I', atom_header[0:4])[0]
                f.seek(atom_size - 8, 1)

        # found 'moov', look for 'mvhd' and timestamps
        atom_header = f.read(ATOM_HEADER_SIZE)
        if atom_header[4:8] == b'cmov':
            raise RuntimeError('moov atom is compressed')
        elif atom_header[4:8] != b'mvhd':
            raise RuntimeError('expected to find "mvhd" header.')
        else:
            f.seek(4, 1)
            creation_time = struct.unpack('>I', f.read(4))[0] - EPOCH_ADJUSTER
            creation_time = DateTime.fromtimestamp(creation_time)
            if creation_time.year < 1990:  # invalid or censored data
                creation_time = None

            modification_time = struct.unpack('>I', f.read(4))[0] - EPOCH_ADJUSTER
            modification_time = DateTime.fromtimestamp(modification_time)
            if modification_time.year < 1990:  # invalid or censored data
                modification_time = None

    return creation_time, modification_time


def rename_media_files(data_path: Path):
    if not data_path.is_dir():
        return

    for i, f in enumerate(data_path.iterdir()):
        if f.name[0] == '.':
            continue
        if f.is_dir():
            continue

        what = whatimage.identify_image(f.open('rb').read())
        if what:
            exif_data = exifread.process_file(f.open('rb'))
            idf_img_dt: exifread.classes.IfdTag = exif_data.get('Image DateTime', None)
            if idf_img_dt:
                s_date, s_time = idf_img_dt.values.split(' ')
                s_date = ''.join(s_date.split(':'))
                if s_date in f.name:
                    continue
                s_time = ''.join(s_time.split(':'))
                img_make = exif_data.get('Image Make', '')
                make_code = MAKE_CODES.get(str(img_make), str(img_make) or 'NA')
                s_f_name = ''.join([
                    s_date,
                    '_',
                    s_time,
                    '000',
                    '_',
                    make_code,
                    f.suffix,
                ])
                new_path = data_path / s_f_name
                f.rename(new_path)
        else:
            try:
                parser = createParser(str(f.absolute()))
            except input.NullStreamError:
                parser = None

            if not parser:
                # print("Unable to parse file", file=stderr)
                # Try get_mov_timestamps
                try:
                    created, modified = get_mov_timestamps(f)
                except Exception as e:
                    # Try TinyTag / Implementation to be done
                    try:
                        print(what, f.name)
                        media = TinyTag.get(f)
                        pprint(media)
                    except TinyTagException:
                        continue
                    continue
                created: DateTime
                s_date = created.strftime('%Y%m%d')
                if s_date in f.name:
                    continue
                s_f_name = ''.join([
                    created.strftime('%Y%m%d_%H%M%S000_mov'),
                    f.suffix,
                ])
                new_path = data_path / s_f_name
                f.rename(new_path)
                continue

            with parser:
                try:
                    metadata: Metadata = extractMetadata(parser)
                except Exception as err:
                    # print("Metadata extraction error: %s" % err, file=stderr)
                    metadata = None

            if not metadata:
                # print("Unable to extract metadata", file=stderr)
                continue

            d_meta = metadata.exportDictionary(human=False)
            for k in ['Common', 'Metadata']:
                created = ''
                producer = ''
                try:
                    created: str = d_meta[k]['creation_date']
                except KeyError:
                    # print(f'Key not found: {k}', file=stderr)
                    continue
                try:
                    producer: str = d_meta[k]['producer'] or 'mov'
                except KeyError:
                    producer = 'mov'

                if bool(created) and bool(producer):
                    break

            s_date, s_time = created.split(' ')
            s_date: str = ''.join(s_date.split('-'))
            if s_date in f.name:
                continue
            s_time: str = ''.join(s_time.split(':'))
            s_f_name = ''.join([
                s_date,
                '_',
                s_time,
                '000',
                '_',
                producer,
                f.suffix,
            ])
            new_path = data_path / s_f_name
            f.rename(new_path)
            continue


def sort_media_files(src: Path, dest=None):
    if not src.is_dir():
        return
    if dest is None:
        dest: Path = src

    re_f_name = re.compile(r"^(\d{8})_(\d{9})_.+$")

    for f in src.iterdir():
        match = re_f_name.match(f.name)
        if match:
            s_date, s_time = match.groups()
            year = s_date[:4]
            month = s_date[4:6]
            s_time = s_time[:6]
            new_img_dir = dest / year / month
            try:
                new_img_dir.mkdir(parents=True, exist_ok=False)
            except FileExistsError:
                pass
            f = f.rename(new_img_dir / f.name)
            print(f.name, f.absolute())


if __name__ == '__main__':
    # Change src and dest path
    # @todo: CLI utility
    src_path = Path.cwd() / 'data'
    dest_path = Path.cwd() / 'data'
    rename_media_files(src_path)
    sort_media_files(src_path, dest_path)
