"""An upstream scraper crash must not read as an app crash.

REPORTED, with a screenshot: scanning a Civitai listing produced a red toast
saying exactly

    string indices must be integers, not 'str'

and nothing else. That is a Python TypeError raised inside gallery-dl's own
Civitai extractor, which reports it as `{'error': 'TypeError', 'message': ...}`
in a type -1 entry. We forwarded the message verbatim.

Three things were wrong with that, and only the third is ours to fix:

  * it names no actor, so it reads as if THIS app broke;
  * it suggests no action, and the user's natural next move — try a different
    URL — cannot work: measured on the real tool, every Civitai listing URL
    fails identically, because the SITE changed shape under the tool;
  * it is indistinguishable from a site REFUSING us (auth, 429, DDoS-Guard),
    which is a completely different problem with a completely different answer.

So a crash class is re-worded and a refusal is passed through untouched.
"""
from app.scrape.sources import gdl


def _entry(error, message):
    return [[-1, {'error': error, 'message': message}]]


def test_an_extractor_crash_names_the_tool_and_says_a_new_url_will_not_help():
    """The reported case, verbatim from gallery-dl."""
    out = gdl._error_sentinel(_entry('TypeError', "string indices must be integers, not 'str'"))
    assert 'gallery-dl' in out, 'the user cannot tell WHO failed'
    assert 'out of date' in out
    assert 'different URL will fix' in out, (
        'the obvious next move is the one that cannot work — it has to say so')
    # The raw text survives inside: a bug report needs it, a user does not lead with it.
    assert "string indices must be integers" in out


def test_every_crash_class_gets_the_same_treatment():
    for kind in ('TypeError', 'KeyError', 'IndexError', 'AttributeError', 'ValueError'):
        assert 'out of date' in gdl._error_sentinel(_entry(kind, 'boom'))


def test_a_site_refusing_us_is_passed_through_untouched():
    """The distinction the rewording exists to preserve. 429, auth and DDoS-Guard
    are the site talking to us, not the tool breaking — their message is already
    the actionable one, and dressing it as 'support is out of date' would send the
    user to fix something that is not broken."""
    for kind, msg in (('HttpError', '429 Too Many Requests'),
                      ('AuthorizationError', 'login required'),
                      ('', 'DDoS-Guard challenge')):
        assert gdl._error_sentinel(_entry(kind, msg)) == msg


def test_a_sentinel_with_nothing_usable_still_says_something():
    assert gdl._error_sentinel(_entry('', '')) == 'gallery-dl: the extractor failed.'
    assert gdl._error_sentinel([[3, 'https://x/y.png', {}]]) is None
