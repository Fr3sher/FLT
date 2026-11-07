"""Real signed presentation bytes, pre-acquisition isolation and bounded input."""
import copy
import hashlib
import io
import struct
import zlib

import pytest
from PIL import Image, PngImagePlugin

from app.plugins.store.catalog import parse_catalog
from app.plugins.store.client import StoreError
from app.plugins.store.media import read_image
from app.plugins.store.media_contract import MAX_MEDIA_BYTES, parse_presentation, validate_image
from test_public_store_tuf import catalog, operator, repository  # noqa: F401


def image_fixture(*, metadata=False):
    buffer = io.BytesIO()
    extra = PngImagePlugin.PngInfo()
    if metadata:
        extra.add_text('Comment', 'review-required')
    Image.new('RGB', (64, 40), (45, 85, 125)).save(buffer, format='PNG', pnginfo=extra)
    data = buffer.getvalue()
    item = {'id': 'workspace', 'target': f'media/camera_angles/1.0.0/{hashlib.sha256(data).hexdigest()}.png',
            'alt': 'Camera angle workspace with a demonstration image', 'caption': 'Choose a viewpoint.',
            'width': 64, 'height': 40}
    return data, item


def media_catalog(*, paid=False):
    value = catalog()
    data, item = image_fixture()
    release = value['products'][0]['releases'][0]
    release['presentation'] = {'schema_version': 1, 'images': [item]}
    if paid:
        release['price'] = {'kind': 'paid', 'product': 'camera-product'}
    return value, data, item


def test_old_catalog_and_empty_presentation_still_parse(repository):
    _, _, config = repository
    release = parse_catalog(catalog(), config)['camera_angles'][0]
    assert release.payload()['presentation']['images'] == []
    assert parse_presentation({'schema_version': 1, 'images': []}, 'camera_angles', '1.0.0') == ()


@pytest.mark.parametrize(('field', 'value'), [
    ('target', 'https://store.invalid/image.png'), ('target', 'file:///private.png'),
    ('target', 'media/camera_angles/1.0.0/../secret.png'),
    ('target', 'media/camera_angles/1.0.0/' + 'a' * 64 + '.svg'),
    ('target', 'media/camera_angles/2.0.0/' + 'a' * 64 + '.png'),
    ('target', 'media/video/1.0.0/' + 'a' * 64 + '.png'),
    ('target', 'media/camera_angles/1.0.0/' + 'a' * 64 + '.png?token=sample'),
    ('target', 'camera/1.0.0.ldsplugin'), ('width', True), ('height', 8193),
    ('alt', ''), ('alt', 'a' * 241), ('caption', 'line\nbreak'), ('id', '../secret'),
])
def test_bad_media_is_rejected_by_catalog(field, value, repository):
    _, _, config = repository
    raw, _, item = media_catalog()
    item[field] = value
    with pytest.raises(StoreError, match='invalid product'):
        parse_catalog(raw, config)


def test_duplicate_excessive_and_unknown_fields_are_rejected():
    _, item = image_fixture()
    for images in ([item, item], [item] * 9, [{**item, 'url': 'https://store.invalid/private'}]):
        with pytest.raises(ValueError):
            parse_presentation({'schema_version': 1, 'images': images}, 'camera_angles', '1.0.0')


def test_content_metadata_dimensions_and_digest_are_checked():
    data, item = image_fixture()
    assert validate_image(data, item) == 'image/png'
    with pytest.raises(ValueError, match='digest'):
        validate_image(data + b'changed', item)
    appended = data + b'private extra bytes' + data[-12:]
    with pytest.raises(ValueError, match='appended'):
        validate_image(appended, {**item, 'target': f'media/camera_angles/1.0.0/{hashlib.sha256(appended).hexdigest()}.png'})
    with pytest.raises(ValueError):
        validate_image(data, {**item, 'width': 63})
    metadata, meta_item = image_fixture(metadata=True)
    with pytest.raises(ValueError):
        validate_image(metadata, meta_item)
    unsafe = b'<svg><script>1</script></svg>'
    with pytest.raises(ValueError):
        validate_image(unsafe, {**item, 'target': f'media/camera_angles/1.0.0/{hashlib.sha256(unsafe).hexdigest()}.png'})


def test_paid_plugin_images_are_public_but_archive_stays_private(repository, monkeypatch):
    public, keys, config = repository
    raw, data, item = media_catalog(paid=True)
    package = b'paid plugin contents'
    private = public.parent / 'paid'
    operator.publish(public, keys, raw, {'camera/1.0.0.ldsplugin': package, item['target']: data}, private_artifacts=private)
    monkeypatch.setattr('app.plugins.store.client.load_config', lambda: config)
    assert read_image('camera_angles', '1.0.0', 'workspace', item['target'].rsplit('/', 1)[-1]) == (data, 'image/png')
    assert not list(public.rglob('*.ldsplugin'))
    assert list(private.rglob('*.ldsplugin'))
    assert list(public.rglob('*.png'))
    # Presentation edits can reuse the same immutable archive and image bytes.
    raw['products'][0]['releases'][0]['presentation']['images'][0]['caption'] = 'Review a viewpoint before installing.'
    operator.publish(public, keys, raw, {}, private_artifacts=private)
    assert len(__import__('json').loads((private / 'registry.json').read_text())['releases']) == 1




def test_bad_media_does_not_partially_publish(repository):
    public, keys, _ = repository
    raw, data, item = media_catalog()
    before = (public / 'metadata/timestamp.json').read_bytes()
    with pytest.raises(ValueError):
        operator.publish(public, keys, raw, {'camera/1.0.0.ldsplugin': b'archive', item['target']: data + b'changed'})
    assert (public / 'metadata/timestamp.json').read_bytes() == before
    assert not list(public.rglob('*.ldsplugin'))


def test_tampered_signed_media_is_refused(repository, monkeypatch):
    public, keys, config = repository
    raw, data, item = media_catalog()
    operator.publish(public, keys, raw, {'camera/1.0.0.ldsplugin': b'archive', item['target']: data})
    next(public.rglob('*.png')).write_bytes(b'changed')
    monkeypatch.setattr('app.plugins.store.client.load_config', lambda: config)
    with pytest.raises(StoreError):
        read_image('camera_angles', '1.0.0', item['id'], item['target'].rsplit('/', 1)[-1])


def test_preparation_preserves_pixels_removes_metadata_and_never_edits_archive(tmp_path):
    from store.tools.prepare_presentation import prepare

    source = tmp_path / 'shot.png'
    data, _ = image_fixture(metadata=True)
    source.write_bytes(data)
    raw = catalog()
    original = copy.deepcopy(raw)
    result, artifacts = prepare(raw, 'camera_angles', '1.0.0', [
        {'file': str(source), 'id': 'workspace', 'alt': 'Camera workspace', 'caption': 'Choose an angle.'}], tmp_path / 'out')
    assert raw == original
    release = result['products'][0]['releases'][0]
    assert release['target'] == original['products'][0]['releases'][0]['target']
    item = release['presentation']['images'][0]
    assert validate_image(artifacts[item['target']], item) == 'image/png'
    assert Image.open(io.BytesIO(data)).tobytes() == Image.open(io.BytesIO(artifacts[item['target']])).tobytes()
    assert not list((tmp_path / 'out').rglob('*.ldsplugin'))


@pytest.mark.parametrize(('format_name', 'extension'), [('JPEG', 'jpg'), ('WEBP', 'webp')])
def test_legacy_still_formats_need_clean_png_export_but_catalog_still_parses(format_name, extension):
    buffer = io.BytesIO()
    Image.new('RGB', (64, 40), (45, 85, 125)).save(buffer, format=format_name)
    data = buffer.getvalue()
    _, item = image_fixture()
    item['target'] = f'media/camera_angles/1.0.0/{hashlib.sha256(data).hexdigest()}.{extension}'
    assert parse_presentation({'schema_version': 1, 'images': [item]}, 'camera_angles', '1.0.0') == (item,)
    with pytest.raises(ValueError, match='cleaned PNG.*prepare_presentation'):
        validate_image(data, item)
    appended = data + b'extra bytes' + data[-2:]
    with pytest.raises(ValueError, match='prepare_presentation'):
        validate_image(appended, {**item, 'target': f'media/camera_angles/1.0.0/{hashlib.sha256(appended).hexdigest()}.{extension}'})


def test_progressive_jpeg_fill_markers_and_image_byte_limit():
    buffer = io.BytesIO()
    Image.new('RGB', (64, 40), (45, 85, 125)).save(buffer, format='JPEG', progressive=True)
    data = buffer.getvalue()[:-2] + b'\xff\xff\xd9'
    _, item = image_fixture()
    item['target'] = f'media/camera_angles/1.0.0/{hashlib.sha256(data).hexdigest()}.jpg'
    with pytest.raises(ValueError, match='prepare_presentation'):
        validate_image(data, item)
    with pytest.raises(ValueError, match='size'):
        validate_image(b'x' * (MAX_MEDIA_BYTES + 1), item)


HIDDEN_CASES = ['png_private_chunk', 'jpeg_unknown_app0', 'jpeg_unknown_app14',
                'jpeg_jfxx_thumbnail', 'webp_private_chunk', 'jpeg_entropy_tail', 'webp_coded_tail']


def hidden_media_fixture(case):
    marker = b'SYNTHETIC_PRIVATE_NOTE'
    format_name = 'PNG' if case.startswith('png') else 'JPEG' if case.startswith('jpeg') else 'WEBP'
    extension = {'PNG': 'png', 'JPEG': 'jpg', 'WEBP': 'webp'}[format_name]
    buffer = io.BytesIO()
    Image.new('RGB', (64, 40), (45, 85, 125)).save(buffer, format=format_name)
    original = buffer.getvalue()
    if case == 'png_private_chunk':
        chunk = b'vpAg' + marker
        data = original[:-12] + struct.pack('>I', len(marker)) + chunk + struct.pack('>I', zlib.crc32(chunk)) + original[-12:]
    elif case == 'webp_private_chunk':
        chunk = b'PRIV' + struct.pack('<I', len(marker)) + marker + (b'\0' if len(marker) % 2 else b'')
        data = original + chunk
        data = data[:4] + struct.pack('<I', len(data) - 8) + data[8:]
    elif case == 'jpeg_entropy_tail':
        data = original[:-2] + marker + original[-2:]
    elif case == 'webp_coded_tail':
        assert original[12:16] == b'VP8 '
        length = int.from_bytes(original[16:20], 'little')
        payload = original[20:20 + length] + marker
        body = b'WEBPVP8 ' + struct.pack('<I', len(payload)) + payload + (b'\0' if len(payload) % 2 else b'')
        data = b'RIFF' + struct.pack('<I', len(body)) + body
    else:
        number = 14 if case == 'jpeg_unknown_app14' else 0
        payload = marker
        if case == 'jpeg_jfxx_thumbnail':
            thumbnail = original[:2] + b'\xff\xfe' + struct.pack('>H', len(marker) + 2) + marker + original[2:]
            payload = b'JFXX\0\x10' + thumbnail
        data = original[:2] + bytes([255, 224 + number]) + struct.pack('>H', len(payload) + 2) + payload + original[2:]
    _, item = image_fixture()
    item['target'] = f'media/camera_angles/1.0.0/{hashlib.sha256(data).hexdigest()}.{extension}'
    return original, data, item


@pytest.mark.parametrize('case', HIDDEN_CASES)
def test_hidden_container_data_is_refused_with_unchanged_visible_pixels(case):
    original, data, item = hidden_media_fixture(case)
    assert b'SYNTHETIC_PRIVATE_NOTE' in data
    assert Image.open(io.BytesIO(original)).tobytes() == Image.open(io.BytesIO(data)).tobytes()
    with pytest.raises(ValueError):
        validate_image(data, item)


@pytest.mark.parametrize('case', HIDDEN_CASES)
def test_raw_publication_refuses_hidden_data_before_any_artifact_write(case, tmp_path):
    _, data, item = hidden_media_fixture(case)
    public, keys, private = tmp_path / 'public', tmp_path / 'keys', tmp_path / 'paid'
    operator.initialize(public, keys)
    before = (public / 'metadata/timestamp.json').read_bytes()
    raw = catalog()
    release = raw['products'][0]['releases'][0]
    release['presentation'] = {'schema_version': 1, 'images': [item]}
    release['price'] = {'kind': 'paid', 'product': 'camera-product'}
    with pytest.raises(ValueError):
        operator.publish(public, keys, raw, {release['target']: b'paid fixture archive', item['target']: data},
                         private_artifacts=private)
    assert (public / 'metadata/timestamp.json').read_bytes() == before
    assert not (public / 'targets/media').exists()
    assert not list(private.rglob('*.ldsplugin'))


@pytest.mark.parametrize('case', HIDDEN_CASES)
def test_reader_refuses_hidden_media_signed_by_an_older_publisher(case, repository, monkeypatch):
    public, keys, config = repository
    _, data, item = hidden_media_fixture(case)
    raw = catalog()
    release = raw['products'][0]['releases'][0]
    release['presentation'] = {'schema_version': 1, 'images': [item]}
    # Test-only old publisher: sign the historical unsafe bytes in this fixture.
    with monkeypatch.context() as legacy:
        legacy.setattr(operator._media, 'validate_image', lambda *_: None)
        operator.publish(public, keys, raw, {release['target']: b'archive fixture', item['target']: data})
    monkeypatch.setattr('app.plugins.store.client.load_config', lambda: config)
    with pytest.raises(StoreError, match='could not be verified'):
        read_image('camera_angles', '1.0.0', item['id'], item['target'].rsplit('/', 1)[-1])


@pytest.mark.parametrize(('format_name', 'mode', 'options'), [
    ('PNG', 'RGB', {}), ('PNG', 'RGBA', {}), ('PNG', 'L', {}), ('PNG', 'LA', {}),
    ('JPEG', 'RGB', {}), ('JPEG', 'L', {}), ('JPEG', 'CMYK', {}),
    ('JPEG', 'RGB', {'progressive': True, 'optimize': True}),
    ('WEBP', 'RGB', {}), ('WEBP', 'RGBA', {}),
    ('WEBP', 'RGB', {'lossless': True}), ('WEBP', 'RGBA', {'lossless': True}),
])
def test_clean_image_profiles_export_as_png_without_additional_pixel_loss(format_name, mode, options, tmp_path):
    from store.tools.prepare_presentation import prepare

    source = Image.new('RGBA', (64, 40))
    source.putdata([(x * 7 % 256, y * 11 % 256, x * y % 256, (x * 3 + y * 5) % 256)
                    for y in range(40) for x in range(64)])
    buffer = io.BytesIO()
    source.convert(mode).save(buffer, format=format_name, **options)
    data = buffer.getvalue()
    _, item = image_fixture()
    extension = {'PNG': 'png', 'JPEG': 'jpg', 'WEBP': 'webp'}[format_name]
    item['target'] = f'media/camera_angles/1.0.0/{hashlib.sha256(data).hexdigest()}.{extension}'
    if format_name == 'PNG':
        assert validate_image(data, item) == 'image/png'
    source_path = tmp_path / ('reviewed.' + extension)
    source_path.write_bytes(data)
    result, artifacts = prepare(catalog(), 'camera_angles', '1.0.0', [
        {'file': str(source_path), 'id': 'cleaned', 'alt': 'Reviewed screenshot'}], tmp_path / 'prepared')
    clean_item = result['products'][0]['releases'][0]['presentation']['images'][0]
    clean = artifacts[clean_item['target']]
    assert validate_image(clean, clean_item) == 'image/png'
    assert Image.open(io.BytesIO(data)).convert('RGBA').tobytes() == Image.open(io.BytesIO(clean)).convert('RGBA').tobytes()


def png_parts(data):
    position = 8
    result = []
    while position < len(data):
        length = int.from_bytes(data[position:position + 4], 'big')
        result.append((data[position + 4:position + 8], data[position + 8:position + 8 + length]))
        position += length + 12
    return result


def test_png_end_checksum_cannot_carry_ignored_bytes():
    original, item = image_fixture()
    data = original[:-4] + b'PRIV'
    item['target'] = f'media/camera_angles/1.0.0/{hashlib.sha256(data).hexdigest()}.png'
    assert Image.open(io.BytesIO(original)).tobytes() == Image.open(io.BytesIO(data)).tobytes()
    with pytest.raises(ValueError, match='prepare_presentation'):
        validate_image(data, item)


@pytest.mark.parametrize('case', ['header_extra', 'compressed_suffix', 'decoded_suffix'])
def test_png_known_chunks_cannot_hide_extra_data(case):
    original, item = image_fixture()
    parts = png_parts(original)
    modified = []
    for kind, payload in parts:
        if kind == b'IHDR' and case == 'header_extra':
            payload += b'private extra bytes'
        if kind == b'IDAT':
            if case == 'compressed_suffix':
                payload += b'private extra bytes'
            elif case == 'decoded_suffix':
                payload = zlib.compress(zlib.decompress(payload) + b'private extra bytes')
        body = kind + payload
        modified.append(struct.pack('>I', len(payload)) + body + struct.pack('>I', zlib.crc32(body)))
    data = original[:8] + b''.join(modified)
    item['target'] = f'media/camera_angles/1.0.0/{hashlib.sha256(data).hexdigest()}.png'
    with pytest.raises(ValueError, match='prepare_presentation'):
        validate_image(data, item)


@pytest.mark.parametrize(('marker', 'header'), [
    (224, b'JFIF\0\1\1\0\0\1\0\1\0\0'), (238, b'Adobe\0d\0\0\0\0\0')])
def test_jpeg_known_app_headers_cannot_have_extra_payload(marker, header):
    buffer = io.BytesIO()
    Image.new('RGB', (64, 40)).save(buffer, format='JPEG')
    original = buffer.getvalue()
    payload = header + b'private extra bytes'
    data = original[:2] + bytes([255, marker]) + struct.pack('>H', len(payload) + 2) + payload + original[2:]
    _, item = image_fixture()
    item['target'] = f'media/camera_angles/1.0.0/{hashlib.sha256(data).hexdigest()}.jpg'
    with pytest.raises(ValueError, match='prepare_presentation'):
        validate_image(data, item)


def test_webp_known_extension_cannot_carry_reserved_header_data():
    buffer = io.BytesIO()
    Image.new('RGBA', (64, 40), (45, 85, 125, 128)).save(buffer, format='WEBP')
    original = buffer.getvalue()
    assert original[12:16] == b'VP8X'
    data = original[:21] + b'PRV' + original[24:]
    _, item = image_fixture()
    item['target'] = f'media/camera_angles/1.0.0/{hashlib.sha256(data).hexdigest()}.webp'
    assert Image.open(io.BytesIO(original)).tobytes() == Image.open(io.BytesIO(data)).tobytes()
    with pytest.raises(ValueError, match='prepare_presentation'):
        validate_image(data, item)


@pytest.mark.parametrize('case', HIDDEN_CASES)
def test_preparation_recovers_hidden_container_inputs_as_clean_png(case, tmp_path):
    from store.tools.prepare_presentation import prepare

    original, data, item = hidden_media_fixture(case)
    source = tmp_path / ('reviewed.' + item['target'].rsplit('.', 1)[-1])
    source.write_bytes(data)
    result, artifacts = prepare(catalog(), 'camera_angles', '1.0.0', [
        {'id': 'cleaned', 'file': str(source), 'alt': 'Reviewed screenshot'}], tmp_path / 'prepared')
    clean_item = result['products'][0]['releases'][0]['presentation']['images'][0]
    clean = artifacts[clean_item['target']]
    assert b'SYNTHETIC_PRIVATE_NOTE' not in clean
    assert validate_image(clean, clean_item) == 'image/png'
    assert Image.open(io.BytesIO(original)).convert('RGB').tobytes() == Image.open(io.BytesIO(clean)).convert('RGB').tobytes()
