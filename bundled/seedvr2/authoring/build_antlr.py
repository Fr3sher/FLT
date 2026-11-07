"""Author-only reproducible wheel build; never invoked by the LDS installer."""
import argparse
import hashlib
import importlib.metadata
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
from urllib.request import urlopen
import zipfile

SOURCE = ('https://files.pythonhosted.org/packages/3e/38/'
          '7859ff46355f76f8d19459005ca000b6e7012f2f1ca597746cbcd1fbfe5e/'
          'antlr4-python3-runtime-4.9.3.tar.gz')
SOURCE_SHA = 'f224469b4168294902bb1efa80a8bf7855f24c99aef99cbefc1bcd3cce77881b'
LICENSE_SHA = 'b1b379fcaf3219593a4c433feb1b35c780bed23fafaae440b1ae2771a9521e3a'
WHEEL_SHA = '4e909ac01d54970b10622e90c2645dad8b186d4d79b5864fa60bb155379173ef'
WHEEL = 'antlr4_python3_runtime-4.9.3+lds.1-py3-none-any.whl'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if os.name != 'nt' or sys.version_info[:2] != (3, 12):
        parser.error('Reproduce this author artifact with Windows Python 3.12.')
    for name, version in [('setuptools', '78.1.0'), ('wheel', '0.46.1')]:
        if importlib.metadata.version(name) != version:
            parser.error(f'The build environment needs {name}=={version}.')
    # Git stores text as LF; Windows checkouts may use CRLF. Hash canonical LF
    # and reproduce the Windows build's line endings when preparing its source.
    licence = (Path(__file__).resolve().parents[1] / 'resources/wheels/LICENSE-ANTLR.txt').read_text(encoding='utf-8')
    if hashlib.sha256(licence.encode('utf-8')).hexdigest() != LICENSE_SHA:
        parser.error('The bundled upstream licence changed.')
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error('Choose an empty output directory; existing artifacts are not overwritten.')
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='lds-antlr-author-') as temporary:
        root = Path(temporary)
        with urlopen(SOURCE, timeout=45) as response:
            body = response.read(1024 * 1024)
        if hashlib.sha256(body).hexdigest() != SOURCE_SHA:
            parser.error('The upstream source archive changed.')
        archive = root / 'source.tar.gz'
        archive.write_bytes(body)
        with tarfile.open(archive) as source:
            if any(not (entry.isfile() or entry.isdir()) for entry in source.getmembers()):
                parser.error('The source archive contains an unexpected entry.')
            source.extractall(root, filter='data')
        source = root / 'antlr4-python3-runtime-4.9.3'
        setup = source / 'setup.py'
        original = setup.read_text(encoding='utf-8')
        if "version='4.9.3'" not in original or 'scripts=["bin/pygrun"]' not in original:
            parser.error('The expected upstream packaging instructions changed.')
        (source / 'LICENSE.txt').write_text(licence, encoding='utf-8')
        setup.write_text(original.replace("version='4.9.3'", "version='4.9.3+lds.1'")
                         .replace('scripts=["bin/pygrun"]', "scripts=[], license_files=['LICENSE.txt']"),
                         encoding='utf-8')
        subprocess.run([sys.executable, '-I', '-m', 'pip', '--isolated', 'wheel',
                        '--no-deps', '--no-build-isolation', '--no-cache-dir',
                        '--wheel-dir', str(output), str(source)], check=True,
                       env={**os.environ, 'SOURCE_DATE_EPOCH': '315532800'})
        wheel = output / WHEEL
        if hashlib.sha256(wheel.read_bytes()).hexdigest() != WHEEL_SHA:
            parser.error('Build output differs from the reviewed artifact; do not distribute it.')
        with zipfile.ZipFile(wheel) as built:
            runtime = [name for name in built.namelist() if name.startswith('antlr4/') and name.endswith('.py')]
            if len(runtime) != 56 or any(built.read(name) != (source / 'src' / name).read_bytes() for name in runtime):
                parser.error('The built runtime differs from upstream.')
    print(f'Verified {WHEEL}: {WHEEL_SHA}')


if __name__ == '__main__':
    main()
