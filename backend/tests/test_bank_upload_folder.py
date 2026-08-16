import io

def test_upload_folder_creates_bank_from_browser_files(client):
    data = {
        'name': 'Uploaded bank',
        'files': [
            (io.BytesIO(b'fake-jpeg-a'), 'myfolder/sub/a.jpg'),
            (io.BytesIO(b'fake-jpeg-b'), 'myfolder/b.png'),
        ],
    }
    resp = client.post('/api/bank/upload-folder', data=data,
                       content_type='multipart/form-data')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['ok'] is True
    assert body['added'] == 2

    list_resp = client.get('/api/banks')
    assert list_resp.status_code == 200
    banks = list_resp.get_json()['banks']
    bank = next((b for b in banks if b['id'] == body['id']), None)
    assert bank is not None
    assert 'bank_uploads' in bank['source_path']


def test_upload_folder_requires_name(client):
    resp = client.post('/api/bank/upload-folder', data={},
                       content_type='multipart/form-data')
    assert resp.status_code == 400
    assert resp.get_json()['error']
