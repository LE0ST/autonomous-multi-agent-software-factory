"""Controller-side behavioral oracle. Sandbox output is untrusted data, never authority."""
import json
import secrets
import string


def _oracle(value):
    return (isinstance(value, str) and len(value) >= 8
            and any(c.isalpha() for c in value) and any(c.isdigit() for c in value))


def _challenges():
    rng = secrets.SystemRandom()
    values = [None, True, False, 0, 123, [], {}, '', 'short', 'abcdefgh', '12345678',
              'Valid123!', '1aaaaaaa', 'aaaaaaa1', 'a1111111', '1111111a',
              'ééééééé1', '字字字字字字字٢', 'a²aaaaaa', '𝒂aaaaaa1', '\x00aaaaaa1']
    # Generate positive, missing-letter, missing-digit and length-boundary cases.
    for _ in range(32):
        n = rng.choice([7, 8, 9, 15, 32, 64, 128])
        letters = ''.join(rng.choice(string.ascii_letters) for _ in range(n))
        digits = ''.join(rng.choice(string.digits) for _ in range(n))
        mixed = list(letters)
        mixed[rng.randrange(n)] = rng.choice(string.digits)
        values.extend([letters, digits, ''.join(mixed), ''.join(mixed[:rng.randrange(0, 8)])])
    rng.shuffle(values)
    return [{'id': secrets.token_hex(24), 'value': v, 'expected': _oracle(v)} for v in values]


def _unique(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValueError('Duplicate JSON key')
        out[k] = v
    return out


def run_all(backend, candidate_dir, scratch_dir):
    # Called only after the controller has materialized and verified the frozen candidate.
    requests = _challenges()
    req_file, resp_file = scratch_dir / 'rpc_request.json', scratch_dir / 'rpc_response.json'
    if req_file.exists() or resp_file.exists():
        return False, '', 'Scratch directory is not fresh'
    req_file.write_text(json.dumps([{'id': r['id'], 'value': r['value']} for r in requests]), encoding='utf-8')
    harness = """import sys,json
sys.path.insert(0, '/src/src')
from auth.password_validator import validate_password
reqs=json.load(open('/scratch/rpc_request.json', encoding='utf-8'))
responses=[]
for r in reqs:
    try:
        value=validate_password(r['value'])
        responses.append({'id':r['id'],'type':type(value).__name__,'value':value})
    except BaseException:
        responses.append({'id':r['id'],'error':'candidate exception'})
with open('/scratch/rpc_response.json','w',encoding='utf-8') as f:
    json.dump({'responses':responses},f)
"""
    (scratch_dir / 'rpc_harness.py').write_text(harness, encoding='utf-8')
    result = backend.execute(['python', '-I', '/scratch/rpc_harness.py'], candidate_dir, scratch_dir, 15.0)
    if result.timed_out or result.exit_code != 0:
        return False, '', 'Candidate execution did not complete successfully'
    try:
        if resp_file.is_symlink() or resp_file.stat().st_size > 262144:
            raise ValueError('Invalid response file')
        data = json.loads(resp_file.read_bytes(), object_pairs_hook=_unique)
        if type(data) is not dict or set(data) != {'responses'} or type(data['responses']) is not list:
            raise ValueError('Invalid response frame')
        frames = data['responses']
        if len(frames) != len(requests):
            raise ValueError('Missing or extra responses')
        responses = {}
        for frame in frames:
            if type(frame) is not dict or set(frame) != {'id', 'type', 'value'}:
                raise ValueError('Invalid response fields')
            if type(frame['id']) is not str or frame['id'] in responses:
                raise ValueError('Duplicate or malformed response ID')
            if frame['type'] != 'bool' or type(frame['value']) is not bool:
                raise ValueError('Candidate value is not a JSON boolean')
            responses[frame['id']] = frame['value']
        if set(responses) != {r['id'] for r in requests}:
            raise ValueError('Response IDs do not match this challenge set')
        if any(responses[r['id']] is not r['expected'] for r in requests):
            raise ValueError('Candidate behavior disagrees with controller oracle')
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        return False, '', str(exc)
    return True, f'{len(requests)} controller behavioral challenges passed; pytest/coverage are supplementary.', ''
