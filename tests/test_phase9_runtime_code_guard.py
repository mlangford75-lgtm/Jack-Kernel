from __future__ import annotations

import sys
import types
from types import SimpleNamespace

import pytest

from jack_runtime_code_guard import (
    RuntimeCodeAuthority,
    RuntimeCodeIntegrityCompromised,
    RuntimeCodeIntegrityUnavailable,
)


def _guard(owner, name="go"):
    guard = RuntimeCodeAuthority()
    guard.register(name="protected", owner=owner, attribute=name)
    guard.seal()
    return guard


def test_unchanged_binding_and_sealed_registration():
    def run(): return "safe"
    owner = SimpleNamespace(go=run)
    guard = _guard(owner)
    guard.verify()
    with pytest.raises(RuntimeError):
        guard.register(name="extra", owner=owner, attribute="go")
    assert guard.state == "ACTIVE"


def test_rebinding_is_terminal_even_after_restoration():
    def run(): return "safe"
    owner = SimpleNamespace(go=run)
    guard = _guard(owner)
    owner.go = lambda: "unsafe"
    with pytest.raises(RuntimeCodeIntegrityCompromised):
        guard.verify()
    owner.go = run
    with pytest.raises(RuntimeCodeIntegrityCompromised):
        guard.verify()


def test_code_object_replacement_is_detected():
    def run(): return "safe"
    def other(): return "unsafe"
    guard = _guard(SimpleNamespace(go=run))
    run.__code__ = other.__code__
    with pytest.raises(RuntimeCodeIntegrityCompromised):
        guard.verify()


def test_constant_only_change_is_detected():
    def run(): return 17
    guard = _guard(SimpleNamespace(go=run))
    run.__code__ = run.__code__.replace(co_consts=(None, 18))
    with pytest.raises(RuntimeCodeIntegrityCompromised):
        guard.verify()


def test_bound_method_descriptor_is_stable():
    class Service:
        def go(self): return 1
    guard = _guard(Service())
    guard.verify()
    assert guard.state == "ACTIVE"


def test_removed_binding_is_confirmed_compromise():
    def run(): return "safe"
    owner = SimpleNamespace(go=run)
    guard = _guard(owner)
    del owner.go
    with pytest.raises(RuntimeCodeIntegrityCompromised):
        guard.verify()
    assert guard.state == "INVALIDATED"


def test_callable_replaced_with_noncallable_is_confirmed():
    owner = SimpleNamespace(go=lambda: "safe")
    guard = _guard(owner)
    owner.go = None
    with pytest.raises(RuntimeCodeIntegrityCompromised):
        guard.verify()


def test_transient_measurement_unavailable_can_be_reverified():
    class Unstable:
        blocked = False
        def __init__(self, fn): self.go = fn
        def __getattribute__(self, name):
            if name == "go" and object.__getattribute__(self, "blocked"):
                raise PermissionError("synthetic unavailable")
            return object.__getattribute__(self, name)
    owner = Unstable(lambda: "safe")
    guard = _guard(owner)
    owner.blocked = True
    with pytest.raises(RuntimeCodeIntegrityUnavailable):
        guard.verify()
    assert guard.state == "SUSPENDED_UNVERIFIED"
    owner.blocked = False
    guard.verify()
    assert guard.state == "ACTIVE"


def test_confirmed_mismatch_outranks_other_slot_measurement_failure():
    class Unstable:
        blocked = False
        def __init__(self, fn): self.go = fn
        def __getattribute__(self, name):
            if name == "go" and object.__getattribute__(self, "blocked"):
                raise PermissionError("synthetic unavailable")
            return object.__getattribute__(self, name)
    fn = lambda: "safe"
    owner = SimpleNamespace(go=fn)
    unstable = Unstable(fn)
    guard = RuntimeCodeAuthority()
    guard.register(name="confirmed", owner=owner, attribute="go")
    guard.register(name="unavailable", owner=unstable, attribute="go")
    guard.seal()
    owner.go = lambda: "changed"
    unstable.blocked = True
    with pytest.raises(RuntimeCodeIntegrityCompromised):
        guard.verify()
    assert guard.mismatched_slots == ("confirmed",)


def test_default_callable_delegate_replacement():
    def good(): return "safe"
    def bad(): return "unsafe"
    def run(delegate=good): return delegate()
    guard = _guard(SimpleNamespace(go=run))
    run.__defaults__ = (bad,)
    with pytest.raises(RuntimeCodeIntegrityCompromised):
        guard.verify()


def test_keyword_only_default_value_change():
    def run(*, permit=False): return permit
    guard = _guard(SimpleNamespace(go=run))
    run.__kwdefaults__["permit"] = True
    with pytest.raises(RuntimeCodeIntegrityCompromised):
        guard.verify()


def test_nested_code_constant_change():
    def run():
        def nested(): return 21
        return nested()
    def changed():
        def nested(): return 22
        return nested()
    guard = _guard(SimpleNamespace(go=run))
    run.__code__ = changed.__code__
    with pytest.raises(RuntimeCodeIntegrityCompromised):
        guard.verify()


def test_closure_delegate_replacement():
    def construct():
        def safe(): return "safe"
        def unsafe(): return "unsafe"
        delegate = safe
        def run(): return delegate()
        return run, unsafe
    run, unsafe = construct()
    guard = _guard(SimpleNamespace(go=run))
    run.__closure__[0].cell_contents = unsafe
    with pytest.raises(RuntimeCodeIntegrityCompromised):
        guard.verify()


def test_mutable_closure_data_is_not_misclassified_as_code():
    state = {"turn": 1}
    def run(): return state["turn"]
    guard = _guard(SimpleNamespace(go=run))
    state["turn"] = 2
    guard.verify()
    assert guard.state == "ACTIVE"


def test_unmeasurable_builtin_is_rejected():
    guard = RuntimeCodeAuthority()
    with pytest.raises(RuntimeCodeIntegrityUnavailable):
        guard.register(name="builtin", owner=SimpleNamespace(go=len), attribute="go")


def test_module_replacement_detected(monkeypatch):
    name = "_phase9_identity_test_module"
    original = types.ModuleType(name)
    monkeypatch.setitem(sys.modules, name, original)
    guard = RuntimeCodeAuthority()
    guard.register(name="fn", owner=SimpleNamespace(go=lambda: 1), attribute="go")
    guard.register_module(name="module", module_name=name)
    guard.seal()
    guard.verify()
    monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    with pytest.raises(RuntimeCodeIntegrityCompromised):
        guard.verify()
    assert guard.mismatched_slots == ("module",)


def test_fastapi_lazily_builds_middleware_without_false_alarm():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    @app.get("/phase9")
    async def protected(): return {"safe": True}
    route = next(x for x in app.routes if getattr(x, "path", None) == "/phase9")
    guard = RuntimeCodeAuthority()
    guard.register(name="endpoint", owner=route, attribute="endpoint")
    guard.register(name="route-app", owner=route, attribute="app")
    guard.register(name="dependant", owner=route.dependant, attribute="call")
    guard.register_route_table(name="routes", app=app)
    guard.seal()
    assert app.middleware_stack is None
    with TestClient(app) as client:
        assert client.get("/phase9").json() == {"safe": True}
    assert app.middleware_stack is not None
    guard.verify()


def test_fastapi_route_app_replacement():
    from fastapi import FastAPI
    app = FastAPI()
    @app.get("/phase9")
    async def protected(): return "safe"
    route = next(x for x in app.routes if getattr(x, "path", None) == "/phase9")
    guard = _guard(route, "app")
    async def bypass(_scope, _receive, _send): pass
    route.app = bypass
    with pytest.raises(RuntimeCodeIntegrityCompromised):
        guard.verify()


def test_fastapi_route_table_extension():
    from fastapi import FastAPI
    app = FastAPI()
    @app.get("/phase9")
    async def protected(): return "safe"
    route = next(x for x in app.routes if getattr(x, "path", None) == "/phase9")
    guard = RuntimeCodeAuthority()
    guard.register(name="endpoint", owner=route, attribute="endpoint")
    guard.register_route_table(name="routes", app=app)
    guard.seal()
    @app.post("/bypass")
    async def bypass(): return "unsafe"
    with pytest.raises(RuntimeCodeIntegrityCompromised):
        guard.verify()


def test_unrelated_runtime_state_does_not_invalidate():
    async def run(_body): return "safe"
    owner = SimpleNamespace(go=run, stage={"turn": 1})
    guard = _guard(owner)
    owner.stage["turn"] = 2
    guard.verify()
    assert guard.state == "ACTIVE"


def test_scoped_model_mismatch_preserves_independent_execution_and_observation():
    model = SimpleNamespace(run=lambda: "model-safe")
    execution = SimpleNamespace(admit=lambda: "executor-safe")
    observation = SimpleNamespace(status=lambda: "healthy")
    guard = RuntimeCodeAuthority()
    guard.register(name="model", owner=model, attribute="run", scope="model")
    guard.register(name="executor", owner=execution, attribute="admit", scope="executor")
    guard.register(name="status", owner=observation, attribute="status", scope="observation")
    guard.seal()
    model.run = lambda: "untrusted"
    with pytest.raises(RuntimeCodeIntegrityCompromised):
        guard.verify_for("model")
    assert guard.state == "INVALIDATED"
    guard.verify_for("executor")
    guard.verify_for("observation")
    assert execution.admit() == "executor-safe"
    assert observation.status() == "healthy"
    with pytest.raises(RuntimeCodeIntegrityCompromised):
        guard.verify_for("model")


def test_scoped_executor_mismatch_keeps_model_and_read_only_status_available():
    model = SimpleNamespace(run=lambda: "safe")
    executor = SimpleNamespace(admit=lambda: "safe")
    guard = RuntimeCodeAuthority()
    guard.register(name="model", owner=model, attribute="run", scope="model")
    guard.register(name="executor", owner=executor, attribute="admit", scope="executor")
    guard.seal()
    executor.admit = lambda: "bypass"
    with pytest.raises(RuntimeCodeIntegrityCompromised):
        guard.verify_for("executor")
    guard.verify_for("model")
    guard.verify_for("observation")


def test_shared_verifier_mismatch_stops_all_scoped_consequences():
    shared = SimpleNamespace(check=lambda: True)
    model = SimpleNamespace(run=lambda: "safe")
    guard = RuntimeCodeAuthority()
    guard.register(name="shared", owner=shared, attribute="check", scope="shared")
    guard.register(name="model", owner=model, attribute="run", scope="model")
    guard.seal()
    shared.check = lambda: False
    with pytest.raises(RuntimeCodeIntegrityCompromised):
        guard.verify_for("observation")
    with pytest.raises(RuntimeCodeIntegrityCompromised):
        guard.verify_for("model")


def test_scoped_temporary_measurement_suspends_only_affected_authority():
    class Unstable:
        def __init__(self):
            self.blocked = False
            self.execute = lambda: 1

        def __getattribute__(self, name):
            if name == "execute" and object.__getattribute__(self, "blocked"):
                raise OSError("synthetic local read failure")
            return object.__getattribute__(self, name)

    owner = Unstable()
    read_only = SimpleNamespace(status=lambda: "healthy")
    guard = RuntimeCodeAuthority()
    guard.register(name="executor", owner=owner, attribute="execute", scope="executor")
    guard.register(name="status", owner=read_only, attribute="status", scope="observation")
    guard.seal()
    owner.blocked = True
    with pytest.raises(RuntimeCodeIntegrityUnavailable):
        guard.verify_for("executor")
    assert guard.state == "SUSPENDED_UNVERIFIED"
    guard.verify_for("observation")
    assert read_only.status() == "healthy"
    owner.blocked = False
    guard.verify_for("executor")
    assert guard.state == "ACTIVE"


def test_full_verify_cannot_clear_confirmed_scoped_invalidation():
    original = lambda: "safe"
    owner = SimpleNamespace(run=original)
    guard = RuntimeCodeAuthority()
    guard.register(name="model", owner=owner, attribute="run", scope="model")
    guard.seal()
    owner.run = lambda: "tampered"
    with pytest.raises(RuntimeCodeIntegrityCompromised):
        guard.verify_for("model")
    owner.run = original
    with pytest.raises(RuntimeCodeIntegrityCompromised):
        guard.verify()
    guard.verify_for("observation")
    assert guard.state == "INVALIDATED"
