"""Pure local contract reproduction. No approval records, privileges or external commands."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
spec = importlib.util.spec_from_file_location('review_guard', HERE/'unit-copy/guard.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
NOW = 1800000000.0
scope = {'preflight': {'path': '/UNIT_ONLY_NOT_OPENED', 'sha256': '0'*64}, 'external_stop': NOW+600}
v3_checkpoint = {'status': 'verified', 'requirement': 'already-private-default-quiescent', 'vm': guard.VM, 'created': NOW-10, 'deadline': NOW+300, 'parent_scope_lease': 'UNIT_ONLY_NO_AUTHORITY', 'default_service_changes_owner': 'parent'}
commands = []
def forbidden_runner(argv, timeout):
    commands.append(argv)
    raise AssertionError('No actual command is permitted')
try:
    guard.guest_inventory(scope, runner=forbidden_runner, clock=lambda: NOW, read=lambda *a, **kw: guard.canonical(v3_checkpoint))
except guard.Blocked as e:
    denied = str(e)
else:
    raise AssertionError('v3 checkpoint unexpectedly accepted')
assert not commands
# Evaluate only the actual admission checkpoint equality expression. No module import,
# no protected objects, no forged reports, no execution of the privileged driver.
path = ROOT/'artex-worker-guest-canary-v3/admission_v3.py'
tree = ast.parse(path.read_text())
call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'need' and len(n.args) == 2 and isinstance(n.args[1], ast.Constant) and n.args[1].value == 'parent preflight checkpoint')
expr = compile(ast.Expression(call.args[0]), str(path), 'eval')
c = {'vm': guard.VM, 'created': NOW-10, 'deadline': NOW+300}
lease = {'handle': 'UNIT_ONLY_NO_AUTHORITY'}
def accepts(checkpoint):
    return eval(expr, {'__builtins__': {}}, {'checkpoint': checkpoint, 'c': c, 'lease': lease})
ready = {'status': 'READY', 'vm': guard.VM, 'created': NOW-10, 'external_stop': NOW+600, 'default_inventory': {'containers': [], 'images': [], 'volumes': []}}
assert accepts(v3_checkpoint) is True
assert accepts(ready) is False
# Same pinned bytes cannot have the mutually exclusive status fields.
assert v3_checkpoint['status'] != ready['status']
result = {'scope': 'UNIT_ONLY_CONTRACT_NO_AUTHORITY', 'v3_checkpoint_accepted_by_actual_v3_predicate': accepts(v3_checkpoint), 'v3_checkpoint_guard_denial': denied, 'guard_ready_checkpoint_accepted_by_actual_v3_predicate': accepts(ready), 'external_commands': commands, 'defect': 'The same context-bound preflight path/hash cannot satisfy both contracts.', 'admission_source_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
print(json.dumps(result, indent=2))
