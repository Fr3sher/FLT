"""Repair typography of declared labels; scene guides never supply identities."""
import re

_SUBJECT = re.compile(r'<Subject\s+(\d+)>', re.I)
_BARE = re.compile(r'(?<![\w<])Subject\s+([0-9]+)(?![\w>])', re.I)
_LITERAL = re.compile(r'<d>.*?</d>|"(?:\\.|[^"\\])*"|«[^»]*»|“[^”]*”|'
                      r"(?<!\w)'[^'\n]+'(?!\w)", re.S)
_VISUAL = re.compile(r'<(?:Picture|Video) \d+>')
_SCENE = re.compile(r'^(?:scene(?: source)?\s*:|(?:the )?(?:opening|current) scene\b|'
                    r'<Picture \d+>\s+(?:supplies|shows|provides)\b.*\b(?:scene|state)\b)', re.I)
_IDENTITY = re.compile(r'\b(?:defined by|identity|new (?:character|creature|person|subject))\b', re.I)
_DENIED_IDENTITY = re.compile(
    r"\b(?:does|do|did)(?:\s+not|n['’]t)\s+"
    r'(?:define|introduce|create|establish|provide|supply)\s+'
    r'(?:(?:a|an|any)\s+)?(?:(?:new|additional|separate)\s+)?'
    r'(?:character|creature|person|subject|identity)\b(?=\s*(?:[.!?]|$))', re.I)
_SOURCE_CLAUSE = re.compile(
    r'\s+(?:and|while|but)\s+(?=(?:(?:whose|his|her|its|their|the)\s+)?'
    r'(?:(?:starting|opening|current)\s+)?(?:identity|pose|posture|position|state)\b)', re.I)
_POSE_CLAUSE = re.compile(
    r'^(?:<Subject \d+>\s+)?(?:(?:whose|his|her|its|their|the)\s+)?'
    r'(?:(?:starting|opening|current)\s+)?(?:pose|posture|position|state)\b', re.I)


def _map_prose(text, transform):
    result, offset = [], 0
    for match in _LITERAL.finditer(text):
        result.extend((transform(text[offset:match.start()]), match[0]))
        offset = match.end()
    return ''.join(result) + transform(text[offset:])


def prose(text):
    """Quoted words are content, not label declarations or visible actions."""
    return _LITERAL.sub('', text)


def subjects(text):
    return set(_SUBJECT.findall(prose(text)))


def canonicalize(fields):
    known = subjects(fields['subject_definitions'])

    def replace(match):
        if match[1] not in known:
            raise ValueError('The model used an undefined subject; try again.')
        return f'<Subject {match[1]}>'

    result = {key: _map_prose(value, lambda text: _BARE.sub(replace, text))
              for key, value in fields.items()}
    if set().union(*(subjects(value) for value in result.values())) - known:
        raise ValueError('The model used an undefined subject; try again.')
    return result


def validate_scene_guides(definitions, references):
    """Reject a guide as an ambiguous identity source, not an extra cast count.

    Identity anchors are collected globally, so scene/pose citations may precede
    them. Explicit identity and pose clauses are validated separately without
    changing the text. Ambiguous bindings still require the writer's repair.
    """
    guides = {r['tag'] for r in references if r['kind'] == 'image'
              and str(r.get('role') or '').strip().casefold() == 'first frame of the video'}
    if not guides:
        return
    identities, previous, clauses = {}, [], []
    for sentence in re.split(r'(?<=[.!?])\s+|\n+', prose(definitions)):
        for clause in _SOURCE_CLAUSE.split(sentence):
            clause = clause.strip()
            numbers = _SUBJECT.findall(clause)
            participants = numbers or previous
            tags = set(_VISUAL.findall(clause))
            scene_tags = tags & guides
            scene = bool(_SCENE.match(clause))
            clauses.append((clause, participants, scene_tags, scene))
            if not scene_tags and not scene and not _POSE_CLAUSE.match(clause):
                for number in participants:
                    identities.setdefault(number, set()).update(tags)
            if numbers and not scene:
                previous = numbers
    for clause, participants, scene_tags, scene in clauses:
        if scene_tags:
            # A complete denial is not a positive identity claim. Inspect a
            # copy only; keep the writer's wording and subject grounding intact.
            identity_claim = _IDENTITY.search(_DENIED_IDENTITY.sub('', clause))
            if (any(not identities.get(number) for number in participants)
                    or (not scene and (not participants or identity_claim))):
                labels = ', '.join(sorted(scene_tags))
                raise ValueError(
                    f'{labels} supplies the opening scene and current state, not a new identity. '
                    'Keep characters defined by their other identity references; describe the '
                    'opening scene separately in subject_definitions. If its identity is ambiguous, '
                    'do not invent or merge a Subject. Rebuild the definitions and shot actions '
                    'using the existing identities; your text is unchanged. Try again.')
