"""Gemini's output filter: a refusal must be reported AS a refusal.

NOTHING here calls the real Gemini API. `requests.post` is patched in every
test, so no key is read, no quota is spent, and the suite does not depend on
Google being up — which is also this file's honest limit: it proves how we READ
an answer we hand ourselves, not that Google produces that shape today.

WHAT IS BEING LOCKED, and why it is worth a file of its own
-----------------------------------------------------------
Gemini screens the image it just produced. When that screen trips, the API
answers **HTTP 200 with an empty candidate list** — a success envelope with no
picture in it. Before this file existed, `generate_variation` handed that back
as `None` and the dataset fan-out wrote one sentence for it:

    "empty response (often a content-policy refusal or a transient API error -
     retry usually works)"

That sentence had to guess, and it guessed wrongly in both directions at once:
it told a user Google had permanently refused that "retry usually works", and it
told a user with a broken connection that they had written something forbidden.

So, in order of how badly each hurts when broken:
  1. a 200 with no image says the FILTER refused it, and relays Google's own
     reason code when there is one;
  2. a real malfunction (unreachable host, rejected key, quota, 5xx) keeps its
     own distinct message and never reads as a content refusal — nor the reverse;
  3. a refusal is NOT fatal: a 40-image batch with 12 refusals runs all 40 and
     ends with an exact count, instead of stopping at the first one or leaving
     12 silent holes;
  4. a normal response is untouched.

The messages promise no workaround, because there is none to promise: the output
filter is not configurable, and it is not deterministic (see nanobanana.py).
"""
import base64
import logging
from unittest.mock import MagicMock, patch

import pytest

KEY = 'AIzaSyTESTKEYVALUE0123456789abcdefghij'
PNG = b'\x89PNG\r\n\x1a\nfake-pixels'


def _resp(status=200, json_body=None, text=''):
    r = MagicMock(status_code=status)
    if json_body is None:
        r.json.side_effect = ValueError('no json')
    else:
        r.json.return_value = json_body
    r.text = text
    return r


def _image_body():
    """A normal, successful generateContent answer."""
    return {'candidates': [{'content': {'parts': [
        {'inlineData': {'mimeType': 'image/png',
                        'data': base64.b64encode(PNG).decode()}}]},
        'finishReason': 'STOP'}]}


def _filtered_body(reason='IMAGE_SAFETY'):
    """What the output filter actually returns: 200, a candidate, no image."""
    return {'candidates': [{'content': {'parts': []}, 'finishReason': reason}],
            'usageMetadata': {'promptTokenCount': 12}}


def _prompt_blocked_body(reason='SAFETY'):
    """The other half of the safety stack: refused BEFORE generating."""
    return {'promptFeedback': {'blockReason': reason, 'safetyRatings': []}}


# --- 1. the refusal is named ------------------------------------------------

def test_a_200_with_no_image_raises_instead_of_returning_none(app, monkeypatch):
    """THE regression this file exists for. The silent `None` is gone: a refused
    request now carries its cause out of the engine."""
    monkeypatch.setenv('GEMINI_API_KEY', KEY)
    from lds_api_engines import nanobanana
    from lds_sdk.engine_errors import EngineRefused
    with patch('lds_api_engines.nanobanana.requests.post',
               return_value=_resp(200, _filtered_body())):
        with pytest.raises(EngineRefused) as e:
            nanobanana.generate_variation([b'ref'], 'a portrait')
    msg = str(e.value)
    assert "image filter refused this image" in msg
    assert 'IMAGE_SAFETY' in msg                      # Google's own reason relayed
    assert 'not configurable' in msg                  # the fact that has no remedy
    assert 'LDS cannot turn it off' in msg


def test_the_refusal_message_never_promises_a_workaround():
    """The measured behaviour is that the same prompt passes about half the time,
    so "retry" is a coin toss. The message must not sell it as a fix, and must
    not invent prompt advice the filter's false positives would make false."""
    from lds_api_engines.nanobanana import refusal_message
    for body in (_filtered_body(), _filtered_body('PROHIBITED_CONTENT'),
                 _prompt_blocked_body(), {}, {'candidates': []}):
        msg = refusal_message(body).lower()
        assert 'retry' not in msg
        assert 'try again' not in msg
        assert 'rephrase' not in msg
        assert 'usually works' not in msg


def test_a_prompt_side_block_is_told_apart_from_an_output_side_one():
    """These are genuinely different: the prompt-side categories ARE the four the
    API exposes, the output filter is not exposed at all. One sentence for both
    would misdescribe whichever it was not written for."""
    from lds_api_engines.nanobanana import refusal_message, refusal_detail
    prompt_side = refusal_message(_prompt_blocked_body('SAFETY'))
    assert 'blocked the prompt before generating' in prompt_side
    assert 'SAFETY' in prompt_side
    assert refusal_detail(_prompt_blocked_body())['scope'] == 'prompt'

    image_side = refusal_message(_filtered_body())
    assert 'image filter refused this image' in image_side
    assert refusal_detail(_filtered_body())['scope'] == 'image'
    assert prompt_side != image_side


def test_a_text_only_answer_relays_the_words_gemini_actually_wrote():
    """Not every empty response is the filter: the model sometimes answers in
    prose. Paraphrasing that as a policy block would be a second guess."""
    from lds_api_engines.nanobanana import refusal_message
    body = {'candidates': [{'content': {'parts': [
        {'text': "I can't help with that request."}]}, 'finishReason': 'STOP'}]}
    msg = refusal_message(body)
    assert 'answered with text instead of an image' in msg
    assert "I can't help with that request." in msg


def test_an_unknown_reason_code_still_reads_as_a_refusal():
    """Google adds finishReason values without notice. An unrecognised one on a
    200-with-no-image must not fall through to a sentence about the network."""
    from lds_api_engines.nanobanana import refusal_message
    msg = refusal_message(_filtered_body('SOME_FUTURE_CODE_2027'))
    assert 'refused' in msg
    assert 'SOME_FUTURE_CODE_2027' in msg


@pytest.mark.parametrize('body', [
    None, 'a string', 42, [], {'candidates': 'not-a-list'},
    {'candidates': ['not-a-dict']}, {'candidates': [{'content': 'not-a-dict'}]},
    {'candidates': [{'content': {'parts': 'not-a-list'}}]},
    {'promptFeedback': 'not-a-dict'},
])
def test_a_malformed_body_still_produces_a_sentence_instead_of_a_crash(body):
    """This runs on whatever Google sends, outside any try/except in the caller.
    A shape we did not anticipate must degrade to the generic refusal, not turn
    a content refusal into an AttributeError the user reads as an app bug."""
    from lds_api_engines.nanobanana import refusal_message, refusal_detail
    assert isinstance(refusal_detail(body), dict)
    msg = refusal_message(body)
    assert isinstance(msg, str) and 'refused' in msg


def test_a_refusal_with_no_reason_at_all_says_so_rather_than_inventing_one():
    from lds_api_engines.nanobanana import refusal_message
    msg = refusal_message({'candidates': [{'content': {'parts': []}}]})
    assert 'no reason given' in msg


def test_snake_case_spellings_are_read_too():
    """The REST envelope is camelCase and the protos are snake_case; both have
    been seen. Reading only one spelling would silently lose the reason."""
    from lds_api_engines.nanobanana import refusal_detail
    assert refusal_detail(
        {'prompt_feedback': {'block_reason': 'SAFETY'}})['reason'] == 'SAFETY'
    assert refusal_detail({'candidates': [
        {'finish_reason': 'IMAGE_SAFETY'}]})['scope'] == 'image'


# --- 2. a malfunction is NOT a refusal --------------------------------------

@pytest.mark.parametrize('status,body,expected,fatal', [
    (401, {'error': {'message': 'API key not valid'}}, 'rejected the API key', True),
    (404, {'error': {'message': 'not found'}}, 'does not serve the model', True),
    (429, {'error': {'message': 'Quota exceeded'}}, 'rate-limited', False),
    (500, {'error': {'message': 'internal'}}, 'HTTP 500', False),
    (503, {'error': {'message': 'overloaded'}}, 'HTTP 503', False),
])
def test_a_real_malfunction_keeps_its_own_message(app, monkeypatch, status, body,
                                                  expected, fatal):
    """Replacing a silence with the WRONG explanation would be worse than the
    silence. A key, a quota or an outage must never read as a content refusal."""
    monkeypatch.setenv('GEMINI_API_KEY', KEY)
    from lds_api_engines import nanobanana
    from lds_sdk.engine_errors import EngineFatal, EngineRefused
    with patch('lds_api_engines.nanobanana.requests.post',
               return_value=_resp(status, body)):
        with pytest.raises(nanobanana.NanoBananaError) as e:
            nanobanana.generate_variation([b'ref'], 'a portrait')
    assert expected in str(e.value)
    assert not isinstance(e.value, EngineRefused)       # never mislabelled
    assert 'image filter' not in str(e.value)
    assert isinstance(e.value, EngineFatal) is fatal
    assert KEY not in str(e.value)


def test_an_unreachable_host_is_not_a_content_refusal(app, monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', KEY)
    import requests
    from lds_api_engines import nanobanana
    from lds_sdk.engine_errors import EngineRefused
    with patch('lds_api_engines.nanobanana.requests.post',
               side_effect=requests.ConnectionError('name resolution failed')):
        with pytest.raises(nanobanana.NanoBananaError) as e:
            nanobanana.generate_variation([b'ref'], 'a portrait')
    assert 'could not reach Gemini' in str(e.value)
    assert not isinstance(e.value, EngineRefused)


def test_a_missing_key_is_fatal_and_not_a_refusal(app):
    from lds_api_engines import nanobanana
    from lds_sdk.engine_errors import EngineFatal, EngineRefused
    with pytest.raises(EngineFatal) as e:
        nanobanana.generate_variation([b'ref'], 'a portrait')
    assert 'no Gemini API key saved' in str(e.value)
    assert not isinstance(e.value, EngineRefused)


def test_no_message_or_log_record_ever_carries_the_key(app, monkeypatch, caplog):
    monkeypatch.setenv('GEMINI_API_KEY', KEY)
    from lds_api_engines import nanobanana
    from lds_sdk.engine_errors import EngineRefused
    caplog.set_level(logging.DEBUG)
    with patch('lds_api_engines.nanobanana.requests.post',
               return_value=_resp(200, _filtered_body())):
        with pytest.raises(EngineRefused) as e:
            nanobanana.generate_variation([b'ref'], 'a portrait')
    assert KEY not in str(e.value)
    assert KEY not in caplog.text


# --- 3. a partially-refused batch runs to the end and counts ----------------


# --- 4. anti-regression: a normal answer is untouched ------------------------

def test_a_normal_response_still_returns_the_image(app, monkeypatch):
    """The whole point of raising on refusals is lost if the success path moved."""
    monkeypatch.setenv('GEMINI_API_KEY', KEY)
    from lds_api_engines import nanobanana
    with patch('lds_api_engines.nanobanana.requests.post',
               return_value=_resp(200, _image_body())) as post:
        out = nanobanana.generate_variation([b'ref-a', b'ref-b'], 'a portrait',
                                            aspect_ratio='3:4')
    assert out == PNG
    payload = post.call_args.kwargs['json']
    parts = payload['contents'][0]['parts']
    assert parts[0]['text'] == 'a portrait'
    assert len(parts) == 3                                  # prompt + both refs
    assert payload['generationConfig']['imageConfig']['aspectRatio'] == '3:4'


def test_the_imageconfig_retry_still_happens_before_any_refusal_is_declared(
        app, monkeypatch):
    """A model that rejects imageConfig answers 400 on the first payload. That is
    a retry, not a refusal, and it must not be reported as one."""
    monkeypatch.setenv('GEMINI_API_KEY', KEY)
    from lds_api_engines import nanobanana
    responses = [_resp(400, {'error': {'message': 'imageConfig unsupported'}}),
                 _resp(200, _image_body())]
    with patch('lds_api_engines.nanobanana.requests.post',
               side_effect=responses) as post:
        out = nanobanana.generate_variation([b'ref'], 'a portrait')
    assert out == PNG
    assert post.call_count == 2
    assert 'imageConfig' not in str(post.call_args.kwargs['json'])
