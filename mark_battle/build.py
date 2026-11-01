# -*- coding: utf-8 -*-
#
# MarkBattle — сборщик мода (.mtmod) для «Мир танков» (Lesta)
#
from __future__ import print_function

import compileall
import os
import shutil
import sys
import zipfile

try:
    _unicode = unicode
except NameError:
    _unicode = str

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
BUILD_DIR = os.path.join(PROJECT_ROOT, 'build')
STAGE_DIRS = ('res', 'mods')
META_FILE = 'meta.xml'
ENTRY_FILE = os.path.join('res', 'scripts', 'client', 'gui', 'mods', 'mod_mark_battle.py')
MOD_ID = 'markbattle'
DEFAULT_VERSION = '1.0.0'
INCLUDE_EXT = frozenset(['.pyc', '.html', '.css', '.js', '.json', '.png',
                         '.svg', '.xml', '.swf'])
EXCLUDE_EXT = frozenset(['.py'])

RES_MAP_REL = os.path.join('mods', 'configs', 'res_map', 'mark_battle.json')
RES_MAP_CONTENT = (
    '[\n'
    '  {\n'
    '    "itemID": "user.markbattle.panel",\n'
    '    "type": "Layout",\n'
    '    "path": "coui://gui/gameface/mods/mark_battle/index.html",\n'
    '    "parameters": {\n'
    '      "extension": "",\n'
    '      "entrance": "MarkBattlePanel",\n'
    '      "impl": "gameface"\n'
    '    }\n'
    '  },\n'
    '  {\n'
    '    "itemID": "user.markbattle.table",\n'
    '    "type": "Layout",\n'
    '    "path": "coui://gui/gameface/mods/mark_battle/table.html",\n'
    '    "parameters": {\n'
    '      "extension": "",\n'
    '      "entrance": "MarkBattleTable",\n'
    '      "impl": "gameface"\n'
    '    }\n'
    '  }\n'
    ']\n'
)

_GLYPHS = (
    (u'\u00ab', u'"'), (u'\u00bb', u'"'),
    (u'\u2014', u'-'), (u'\u2013', u'-'),
    (u'\u2026', u'...'),
    (u'\u2019', u"'"), (u'\u2018', u"'"),
)


def P(msg):
    if not isinstance(msg, _unicode):
        msg = msg.decode('utf-8', 'replace')
    for src, dst in _GLYPHS:
        msg = msg.replace(src, dst)
    if _unicode is str:
        print(msg)
        return
    enc = getattr(sys.stdout, 'encoding', None) or 'utf-8'
    try:
        data = msg.encode(enc, 'replace')
    except (LookupError, UnicodeError):
        data = msg.encode('utf-8', 'replace')
    print(data)


def _fail(msg):
    P(u'[BUILD][ERROR] %s' % msg)
    sys.exit(1)


def parse_args(argv):
    version = DEFAULT_VERSION
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ('-v', '--version'):
            if i + 1 >= len(argv):
                _fail(u'After %s a version is required, e.g.: -v 1.0.0' % arg)
            version = argv[i + 1]
            i += 2
        elif arg in ('-h', '--help'):
            P(u'Usage: python build.py -v <version> [--force]')
            sys.exit(0)
        elif arg == '--force':
            i += 1
        else:
            _fail(u'Unknown argument: %s (see -h)' % arg)
    return version


def check_interpreter():
    major, minor = sys.version_info[0], sys.version_info[1]
    if major != 2 or minor != 7:
        P(u'=' * 62)
        P(u'[BUILD][WARNING] Running under Python %d.%d, client uses 2.7!' % (major, minor))
        P(u'=' * 62)
        if '--force' not in sys.argv:
            _fail(u'Refusing to compile with wrong interpreter. Add --force to continue.')
    else:
        P(u'[BUILD] Interpreter: Python %d.%d.%d - OK'
          % (major, minor, sys.version_info[2]))


def sync_gameface_assets():
    src = os.path.join(PROJECT_ROOT, 'res', 'gui', 'gameface')
    dst = os.path.join(PROJECT_ROOT, 'mods', 'gui', 'gameface')
    if not os.path.isdir(src):
        P(u'[BUILD][WARNING] missing %s - sync skipped' % src)
    else:
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        P(u'[BUILD] Assets synced: res/gui/gameface -> mods/gui/gameface')

    res_map_path = os.path.join(PROJECT_ROOT, RES_MAP_REL)
    res_map_dir = os.path.dirname(res_map_path)
    if not os.path.isdir(res_map_dir):
        os.makedirs(res_map_dir)
    with open(res_map_path, 'wb') as f:
        f.write(RES_MAP_CONTENT.encode('utf-8'))
    P(u'[BUILD] res_map updated: %s' % RES_MAP_REL)


def stage_sources():
    sync_gameface_assets()
    if os.path.isdir(BUILD_DIR):
        shutil.rmtree(BUILD_DIR)
    os.makedirs(BUILD_DIR)
    for name in STAGE_DIRS:
        src = os.path.join(PROJECT_ROOT, name)
        if not os.path.isdir(src):
            _fail(u'Folder "%s" not found in project root!' % name)
        dst = os.path.join(BUILD_DIR, name)
        shutil.copytree(src, dst)
    meta_src = os.path.join(PROJECT_ROOT, META_FILE)
    if not os.path.isfile(meta_src):
        _fail(u'%s not found!' % META_FILE)
    shutil.copy2(meta_src, os.path.join(BUILD_DIR, META_FILE))
    P(u'[BUILD] Staging: res/ + mods/ + meta.xml -> build/')


def substitute_version(version):
    targets = [
        os.path.join(BUILD_DIR, META_FILE),
        os.path.join(BUILD_DIR, *ENTRY_FILE.replace('\\', '/').split('/')),
    ]
    marker = '{{VERSION}}'
    for path in targets:
        if not os.path.isfile(path):
            _fail(u'Not found (after staging): %s' % path)
        with open(path, 'rb') as f:
            content = f.read()
        mb = marker.encode('utf-8')
        vb = version.encode('utf-8')
        if mb in content:
            content = content.replace(mb, vb)
            with open(path, 'wb') as f:
                f.write(content)
            P(u'[BUILD] Version %s substituted into %s'
              % (version, os.path.relpath(path, BUILD_DIR)))


def compile_python():
    ok = compileall.compile_dir(BUILD_DIR, quiet=1, force=True)
    if not ok:
        _fail(u'Python compilation failed.')
    for root, dirs, _files in os.walk(BUILD_DIR):
        for d in list(dirs):
            if d == '__pycache__':
                cache_dir = os.path.join(root, d)
                for fname in os.listdir(cache_dir):
                    if fname.endswith('.pyc'):
                        base = fname.split('.')[0] + '.pyc'
                        shutil.move(os.path.join(cache_dir, fname),
                                    os.path.join(root, base))
                shutil.rmtree(cache_dir)
                dirs.remove(d)
    P(u'[BUILD] Compiled .py -> .pyc')


def pack_mtmod(version):
    out_name = '%s_%s.mtmod' % (MOD_ID, version)
    out_path = os.path.join(PROJECT_ROOT, out_name)
    if os.path.exists(out_path):
        os.remove(out_path)

    count = 0
    with zipfile.ZipFile(out_path, 'w', zipfile.ZIP_STORED) as zf:
        for root, dirs, files in os.walk(BUILD_DIR):
            dirs.sort()
            for fname in sorted(files):
                ext = os.path.splitext(fname)[1].lower()
                if ext in EXCLUDE_EXT:
                    continue
                if ext not in INCLUDE_EXT:
                    continue
                full = os.path.join(root, fname)
                arcname = os.path.relpath(full, BUILD_DIR).replace(os.sep, '/')
                zf.write(full, arcname)
                count += 1
    size_kb = os.path.getsize(out_path) / 1024.0
    P(u'[BUILD] Files packed: %d' % count)
    P(u'[BUILD] DONE: %s (%.1f KB)' % (out_name, size_kb))
    P(u'[BUILD] Install to: <game>/mods/<version>/')
    return out_path


def main():
    P(u'=' * 62)
    P(u'  MarkBattle builder - Mir Tankov (Lesta), Gameface edition')
    P(u'=' * 62)
    version = parse_args(sys.argv[1:])
    check_interpreter()
    stage_sources()
    substitute_version(version)
    compile_python()
    pack_mtmod(version)
    P(u'[BUILD] Ready.')


if __name__ == '__main__':
    main()