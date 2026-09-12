"""One-shot, local-only Qwen3-VL-Reranker-2B for at most 20 Bank images.

Image-only adaptation of QwenLM/Qwen3-VL-Embedding's Apache-2.0 scorer,
revision 393e2978d27852b0d0230d6994f37f9c15bed73c. It preserves the official
prompt and yes-minus-no head. Invalid images never become text-only inputs.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import sys

INSTRUCTION = 'Retrieve images relevant to the search query.'
MAX_PIXELS = 524288
MAX_LENGTH = 4096


def conversation(query, image):
    return [
        {'role': 'system', 'content': [{'type': 'text', 'text':
            'Judge whether the Document meets the requirements based on the Query '
            'and the Instruct provided. Note that the answer can only be "yes" or "no".'}]},
        {'role': 'user', 'content': [
            {'type': 'text', 'text': '<Instruct>: ' + INSTRUCTION},
            {'type': 'text', 'text': '<Query>:'},
            {'type': 'text', 'text': query},
            {'type': 'text', 'text': '\n<Document>:'},
            {'type': 'image', 'image': image, 'min_pixels': 4096,
             'max_pixels': MAX_PIXELS}]}]


def validate_request(data):
    if not isinstance(data, dict):
        raise ValueError('request must be an object')
    query = data.get('query')
    if not isinstance(query, str) or not query.strip() or len(query) > 512:
        raise ValueError('invalid query')
    images = data.get('images')
    if not isinstance(images, list) or not 1 <= len(images) <= 20:
        raise ValueError('invalid candidate count')
    ids = []
    for item in images:
        if not isinstance(item, dict) or type(item.get('id')) is not int:
            raise ValueError('invalid candidate')
        path = item.get('path')
        if not isinstance(path, str) or not Path(path).is_absolute():
            raise ValueError('only local image files are accepted')
        sha = item.get('sha256')
        if not isinstance(sha, str) or len(sha) != 64:
            raise ValueError('missing image fingerprint')
        ids.append(item['id'])
    if len(set(ids)) != len(ids):
        raise ValueError('duplicate candidate')
    if data.get('device') not in ('cpu', 'cuda'):
        raise ValueError('invalid device')
    if not isinstance(data.get('model_path'), str) or not Path(data['model_path']).is_dir():
        raise ValueError('local model is unavailable')


def run(data):
    validate_request(data)
    import torch
    from PIL import Image, ImageOps
    from qwen_vl_utils import process_vision_info
    from transformers import AutoProcessor, Qwen3VLForConditionalGeneration
    from bank_image_guard import read_validated_bank_image

    device = data['device']
    if device == 'cuda' and not torch.cuda.is_available():
        raise RuntimeError('CUDA is unavailable')
    dtype = torch.bfloat16 if device == 'cuda' else torch.float32
    lm = Qwen3VLForConditionalGeneration.from_pretrained(
        data['model_path'], local_files_only=True, trust_remote_code=False,
        torch_dtype=dtype, attn_implementation='sdpa').to(device).eval()
    processor = AutoProcessor.from_pretrained(
        data['model_path'], local_files_only=True, trust_remote_code=False,
        padding_side='left')
    vocab = processor.tokenizer.get_vocab()
    head = torch.nn.Linear(lm.lm_head.weight.shape[1], 1, bias=False)
    with torch.no_grad():
        head.weight[0] = (lm.lm_head.weight[vocab['yes']]
                          - lm.lm_head.weight[vocab['no']]).float().cpu()
    head = head.to(device=device, dtype=dtype).eval()
    model = lm.model.eval()
    model.config.use_cache = False
    if hasattr(model.config, 'text_config'):
        model.config.text_config.use_cache = False
    del lm
    results = []
    with torch.inference_mode():
        for item in data['images']:
            payload = read_validated_bank_image(item['path'])
            if hashlib.sha256(payload).hexdigest() != item['sha256']:
                raise ValueError('candidate changed during refinement')
            with Image.open(io.BytesIO(payload)) as raw:
                image = ImageOps.exif_transpose(raw).convert('RGB')
            pair = conversation(data['query'], image)
            text = processor.apply_chat_template([pair], tokenize=False,
                                                 add_generation_prompt=True)
            images, _, _ = process_vision_info(
                [pair], image_patch_size=16, return_video_kwargs=True,
                return_video_metadata=True)
            inputs = processor(text=text, images=images, truncation=False,
                               padding=True, do_resize=False, return_tensors='pt')
            if ('pixel_values' not in inputs or inputs['pixel_values'].numel() == 0
                    or inputs['input_ids'].shape[-1] > MAX_LENGTH):
                raise ValueError('image or query exceeds the refinement budget')
            if 'mm_token_type_ids' in inputs:
                if inputs['mm_token_type_ids'].shape != inputs['input_ids'].shape:
                    raise ValueError('inconsistent multimodal tokens')
            inputs = inputs.to(device)
            score = torch.sigmoid(head(model(**inputs).last_hidden_state[:, -1]))
            if not torch.isfinite(score).all():
                raise RuntimeError('non-finite refinement score')
            results.append({'id': item['id'], 'score': float(score.item())})
    return {'ok': True, 'results': results, 'device': device}


if __name__ == '__main__':
    try:
        raw = sys.stdin.buffer.read(65537)
        if len(raw) > 65536:
            raise ValueError('request is too large')
        print(json.dumps(run(json.loads(raw))))
    except Exception as exc:
        # Avoid returning local paths or model internals through a public API.
        print(json.dumps({'ok': False, 'error': type(exc).__name__}))
        sys.exit(1)
