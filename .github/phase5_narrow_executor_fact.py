from pathlib import Path


def replace(path_str, old, new, count=1):
    path = Path(path_str)
    text = path.read_text(encoding='utf-8')
    found = text.count(old)
    if found != count:
        raise RuntimeError(f'{path}: expected {count} matches, found {found}')
    path.write_text(text.replace(old, new, count), encoding='utf-8', newline='\n')

replace(
    'jack_consequence_gate.py',
    '''@dataclass(frozen=True)\nclass ExecutorAdmissionIdentityFact:\n    runtime_matches: bool\n    lane_matches: bool\n    call_matches: bool = True\n''',
    '''@dataclass(frozen=True)\nclass ExecutorAdmissionIdentityFact:\n    """Live Phase-5 identity facts currently integrated at executor admission.\n\n    Exact pending tool-call correlation remains owned by the existing Phase-4\n    admission mechanism until its raw-fact seam is centralized without changing\n    validation order or blast radius.\n    """\n\n    runtime_matches: bool\n    lane_matches: bool\n''',
)
replace(
    'jack_consequence_gate.py',
    '        ok = fact.runtime_matches and fact.lane_matches and fact.call_matches\n',
    '        ok = fact.runtime_matches and fact.lane_matches\n',
)
replace(
    'jack_consequence_gate.py',
    'ExecutorAdmissionIdentityFact(runtime_matches=runtime_matches, lane_matches=lane_matches, call_matches=True)',
    'ExecutorAdmissionIdentityFact(runtime_matches=runtime_matches, lane_matches=lane_matches)',
)

for path_str in ('tests/test_phase5_consequence_gate.py',):
    path = Path(path_str)
    text = path.read_text(encoding='utf-8')
    text = text.replace('gate.ExecutorAdmissionIdentityFact(False, True, True)', 'gate.ExecutorAdmissionIdentityFact(False, True)')
    path.write_text(text, encoding='utf-8', newline='\n')

Path(__file__).unlink()
