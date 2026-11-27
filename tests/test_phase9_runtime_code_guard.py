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


def test_exception_handler_registry_is_sealed_and_terminal():
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient
    app = FastAPI()

    @app.exception_handler(HTTPException)
    async def safe(request, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=exc.status_code, content={"detail": "safe"})

    guard = RuntimeCodeAuthority()
    guard.register(name="handler", owner=SimpleNamespace(fn=safe), attribute="fn")
    guard.register_exception_handlers(name="handlers", app=app)
    guard.seal()
    with TestClient(app):
        guard.verify_for("observation")
    app.exception_handlers[HTTPException] = lambda *_: None
    with pytest.raises(RuntimeCodeIntegrityCompromised):
        guard.verify_for("model")
    app.exception_handlers[HTTPException] = safe
    with pytest.raises(RuntimeCodeIntegrityCompromised):
        guard.verify_for("observation")


def test_p1_immutable_code_memo_replays_exact_fingerprint_and_live_defaults():
    from jack_runtime_code_guard import _function_shape

    def make(value):
        def nested():
            return ("literal", 123, frozenset({1, 2}))
        def fn(*, flag=False):
            return nested(), value, flag
        return fn

    first, second = make(1), make(2)
    memo = {}
    for fn in (first, second, first, second):
        assert _function_shape(fn, memo) == _function_shape(fn)
    assert id(first.__code__) in memo
    assert first.__code__ is second.__code__
    old = _function_shape(first, memo)
    first.__kwdefaults__["flag"] = True
    assert _function_shape(first, memo) == _function_shape(first) != old
    # The function identity is not part of the cached code subtree.
    assert _function_shape(first, memo) != _function_shape(second, memo)


def test_p1_code_with_mutable_executable_constant_is_never_memoized():
    from jack_runtime_code_guard import _function_shape

    def delegate():
        return "first"
    def changed():
        return "second"
    def fn():
        return None

    fn.__code__ = fn.__code__.replace(co_consts=(None, delegate))
    memo = {}
    old = _function_shape(fn, memo)
    assert id(fn.__code__) not in memo
    delegate.__code__ = changed.__code__
    assert _function_shape(fn, memo) == _function_shape(fn) != old


def test_p1_warm_code_memo_preserves_depth_and_node_limits():
    from jack_runtime_code_guard import _function_shape

    def delegate():
        return 1
    def fn():
        return None

    memo = {}
    _function_shape(delegate, memo)
    deep = delegate
    for _ in range(19):
        deep = (deep,)
    fn.__defaults__ = (deep,)
    for cache in (None, memo):
        with pytest.raises(RuntimeCodeIntegrityUnavailable, match="measurement limits"):
            _function_shape(fn, cache)
    fn.__defaults__ = (tuple(delegate for _ in range(1000)),)
    for cache in (None, memo):
        with pytest.raises(RuntimeCodeIntegrityUnavailable, match="measurement limits"):
            _function_shape(fn, cache)


def test_p1_sealed_code_memo_never_masks_code_replacement():
    def run():
        return "safe"

    first = SimpleNamespace(go=run)
    second = SimpleNamespace(go=run)
    guard = RuntimeCodeAuthority()
    guard.register(name="one", owner=first, attribute="go")
    guard.register(name="two", owner=second, attribute="go")
    guard.seal()
    guard.verify_for("model")
    run.__code__ = run.__code__.replace(co_consts=(None, "changed"))
    with pytest.raises(RuntimeCodeIntegrityCompromised):
        guard.verify_for("model")


@pytest.mark.parametrize("mutation", ["default", "closure", "mutable_constant"])
def test_p1_sealed_transcripts_do_not_cache_live_dependencies(mutation):
    def delegate():
        return "safe"

    def replacement():
        return "changed"

    if mutation == "default":
        def run(*, callback=delegate):
            return callback()
    elif mutation == "closure":
        def run():
            return delegate()
    else:
        def run():
            return None
        run.__code__ = run.__code__.replace(co_consts=(None, delegate))

    guard = _guard(SimpleNamespace(go=run))
    baseline = guard._sealed_code_transcripts
    assert len(baseline) <= 128
    if mutation == "mutable_constant":
        # A sole slot containing mutable executable constants may yield no
        # eligible startup transcripts at all. The live traversal is required.
        assert id(run.__code__) not in baseline
    else:
        assert baseline
        assert id(run.__code__) in baseline
    for _ in range(3):
        guard.verify_for("model")
        assert guard._sealed_code_transcripts is baseline
    if mutation == "default":
        run.__kwdefaults__["callback"] = replacement
    elif mutation == "closure":
        run.__closure__[0].cell_contents = replacement
    else:
        delegate.__code__ = replacement.__code__
    with pytest.raises(RuntimeCodeIntegrityCompromised):
        guard.verify_for("model")
    assert guard.state == "INVALIDATED"


def test_p1_unfamiliar_equivalent_code_does_not_enroll_in_sealed_memo():
    def run():
        return "safe"

    guard = _guard(SimpleNamespace(go=run))
    baseline = guard._sealed_code_transcripts
    original = run.__code__
    assert id(original) in baseline
    run.__code__ = original.replace()
    assert run.__code__ is not original
    guard.verify_for("model")
    assert guard._sealed_code_transcripts is baseline
    assert id(run.__code__) not in baseline
    with pytest.raises(TypeError):
        baseline[id(run.__code__)] = None
