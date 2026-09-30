from pathlib import Path

path = Path('tests/test_surgical_regressions.py')
text = path.read_text(encoding='utf-8')
old = '''        "jack_evidence_guard.py",\n        "jack_path_policy.py",\n        "jack_responses_compat.py",\n'''
new = '''        "jack_evidence_guard.py",\n        "jack_path_policy.py",\n        "jack_consequence_gate.py",\n        "jack_responses_compat.py",\n'''
if text.count(old) != 1:
    raise RuntimeError(f'expected one direct-entrypoint manifest set, found {text.count(old)}')
path.write_text(text.replace(old, new, 1), encoding='utf-8', newline='\n')
Path(__file__).unlink()
