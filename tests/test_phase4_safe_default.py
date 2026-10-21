"""Phase 4 safe default: allow narrowly verified system reads, retain dangerous-operation boundaries."""
import json
import pytest
import jack_path_policy as p

ENV={"SystemRoot":r"C:\Windows","WINDIR":r"C:\Windows","SystemDrive":"C:","USERPROFILE":r"C:\Users\Operator"}

def policy(*, workspace=None, never=()):
    return p.build_runtime_path_policy(runtime_id="phase4-default-test",lane_id="lane",raw_json=json.dumps({"version":1,"workspace_root":workspace,"never_paths":list(never)}),host_environment=ENV)

def call(tool,arguments):
    return {"id":"test","type":"function","function":{"name":tool,"arguments":json.dumps(arguments)}}

def structured(tool,path,config=None):
    return p.authorize_structured_tool_call(config or policy(),call(tool,{"path":path}))

def command(text,tool="bash",config=None):
    return p.authorize_command_tool_call(config or policy(),call(tool,{"command":text}),executor_cwd=r"D:\Work",executor_platform="win32",command_dialect=("powershell" if tool=="powershell" else "bash"))

@pytest.mark.parametrize("name",["read","ls"])
def test_verified_structured_read_allowed(name):
    assert structured(name,r"C:\Windows\System32\drivers\etc\hosts").outcome is p.PathAuthorizationOutcome.ALLOW

@pytest.mark.parametrize("name",["write","edit"])
def test_structured_system_mutations_still_hard(name):
    assert structured(name,r"C:\Windows\System32\drivers\etc\hosts").outcome is p.PathAuthorizationOutcome.HARD_INTERRUPT

@pytest.mark.parametrize("target",[
    r"C:\Windows\System32\config\SAM",
    r"C:\Windows\System32\Tasks\MyTask",
    r"C:\Windows\System32\GroupPolicy\Machine\Registry.pol",
    r"C:\Windows\Panther\unattend.xml",
])
def test_sensitive_system_reads_recoverably_denied(target):
    assert structured("read",target).outcome is p.PathAuthorizationOutcome.DENY_AND_CONTINUE

def test_explicit_never_path_remains_hard_for_read():
    cfg=policy(never=[r"C:\Windows\System32\drivers"])
    assert structured("read",r"C:\Windows\System32\drivers\etc\hosts",cfg).outcome is p.PathAuthorizationOutcome.HARD_INTERRUPT

def test_workspace_lock_keeps_read_outside_denied():
    cfg=policy(workspace=r"D:\Work")
    assert structured("read",r"C:\Windows\System32\drivers\etc\hosts",cfg).outcome is p.PathAuthorizationOutcome.DENY_AND_CONTINUE

@pytest.mark.parametrize("text",[
    'cat "/c/Windows/System32/drivers/etc/hosts"',
    'ls "/c/Windows/System32"',
])
def test_simple_bash_system_read_allowed(text):
    assert command(text).outcome is p.PathAuthorizationOutcome.ALLOW

def test_simple_powershell_read_allowed():
    assert command('Get-Content -LiteralPath "C:\\Windows\\System32\\drivers\\etc\\hosts"',tool="powershell").outcome is p.PathAuthorizationOutcome.ALLOW

@pytest.mark.parametrize("text",[
    'rm "/c/Windows/System32/drivers/etc/hosts"',
    'cp README.md "/c/Windows/System32/drivers/etc/hosts"',
    'cat "/c/Windows/System32/drivers/etc/hosts" | tee copy.txt',
    'bash -c "cat /c/Windows/System32/drivers/etc/hosts"',
])
def test_unknown_mutating_or_composite_shell_commands_not_exempt(text):
    assert command(text).outcome is p.PathAuthorizationOutcome.HARD_INTERRUPT

def test_sensitive_shell_read_recoverably_denied():
    assert command('cat "/c/Windows/System32/config/SAM"').outcome is p.PathAuthorizationOutcome.DENY_AND_CONTINUE

def test_bash_system_read_under_workspace_lock_denied():
    assert command('cat "/c/Windows/System32/drivers/etc/hosts"',config=policy(workspace=r"D:\Work")).outcome is p.PathAuthorizationOutcome.DENY_AND_CONTINUE

def test_raw_path_policy_remains_hard_to_prevent_bypasses():
    assert p.authorize_represented_path(policy(),r"C:\Windows\System32\drivers\etc\hosts").outcome is p.PathAuthorizationOutcome.HARD_INTERRUPT
