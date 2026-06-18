# L1.5 Tiered Cognition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an on-device L1.5 cognition tier — a `TieredCognitionBackend` composing a fast local VLM, a deep cloud/LAN 7B, and a rules fallback — so most events are handled locally and the robot keeps working when the 7B is offline.

**Architecture:** New `TieredCognitionBackend` (a drop-in `CognitionBackend`) + `TierPolicy` (pure dataclass) in `cognition.py`. It reuses the existing `LocalVLMBackend`/`qwen_client` (fast = RDK-local small VLM, deep = Mac 7B, both OpenAI-compatible, differ only by `base_url`) and `MockCognitionBackend` (rules fallback). Config + node wiring select it via `backend: tiered`. The on-RDK small-model runtime is out of scope (on-board work).

**Tech Stack:** Python 3 stdlib only in the core (dataclasses, urllib.error). Tests: `unittest` with injected fakes (no mock library, no model, no ROS). Package: `rdk_x5/ros2_ws/src/inspection_manager`.

## Global Constraints

- Core modules use **stdlib + `.escalation`/`.events` only** — no numpy/cv2/rclpy/model deps in `cognition.py`. (`cognition.py` must stay importable off-board.)
- Tests use **`unittest`**, `sys.path.insert(0, PACKAGE_SRC)`, and **inject fake objects** (no `unittest.mock`, no real model). Run with `python3 -m unittest`, never pytest.
- **Do NOT modify** `CognitionRequest`/`CognitionResult` fields, `actions.py`, `escalation.py` gate1/gate2, `report*`/L3, or any downstream.
- `CognitionResult` fields (verbatim): `explanation: str`, `confirmed_severity: str`, `suggested_actions: List[str]`, `escalate_to_cloud: bool`, `confidence: float`, `reason: str`.
- `HazardEvent` required positional fields (verbatim, from `events.py`): `event_id, timestamp, station_id, source, event_type, severity` then optional `confidence=0.0, summary="", evidence, action`.
- `CognitionBackend` protocol: `assess(self, request: CognitionRequest) -> CognitionResult`.
- Commit messages end with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- PACKAGE_SRC for tests = `Path(__file__).resolve().parents[1] / "rdk_x5" / "ros2_ws" / "src" / "inspection_manager"`.

---

### Task 1: `TierPolicy` dataclass + `tier_policy_from_dict`

**Files:**
- Modify: `rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/cognition.py` (add near the other dataclasses, after `CognitionResult`)
- Test: `tests/test_tiered_cognition.py` (create)

**Interfaces:**
- Produces:
  - `TierPolicy(escalate_below_confidence: float = 0.6, critical_always_deep: bool = True, escalate_if_fast_critical: bool = True)` — a `@dataclass`.
  - `tier_policy_from_dict(cfg: dict) -> TierPolicy` — pure reader, tolerates `None`/missing keys.

- [ ] **Step 1: Write the failing test**

Create `tests/test_tiered_cognition.py`:

```python
import sys
import unittest
from pathlib import Path

PACKAGE_SRC = (
    Path(__file__).resolve().parents[1]
    / "rdk_x5" / "ros2_ws" / "src" / "inspection_manager"
)
sys.path.insert(0, str(PACKAGE_SRC))

from inspection_manager.cognition import TierPolicy, tier_policy_from_dict  # noqa: E402


class TierPolicyTests(unittest.TestCase):
    def test_defaults(self):
        p = TierPolicy()
        self.assertEqual(p.escalate_below_confidence, 0.6)
        self.assertTrue(p.critical_always_deep)
        self.assertTrue(p.escalate_if_fast_critical)

    def test_from_dict_reads_values(self):
        p = tier_policy_from_dict(
            {"escalate_below_confidence": 0.4, "critical_always_deep": False,
             "escalate_if_fast_critical": False}
        )
        self.assertEqual(p.escalate_below_confidence, 0.4)
        self.assertFalse(p.critical_always_deep)
        self.assertFalse(p.escalate_if_fast_critical)

    def test_from_dict_tolerates_none_and_missing(self):
        p = tier_policy_from_dict(None)
        self.assertEqual(p.escalate_below_confidence, 0.6)
        self.assertTrue(p.critical_always_deep)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_tiered_cognition -v`
Expected: FAIL — `ImportError: cannot import name 'TierPolicy'`.

- [ ] **Step 3: Write minimal implementation**

In `cognition.py`, add after the `CognitionResult` dataclass (the `field` import is already present at the top of the file):

```python
@dataclass
class TierPolicy:
    """Thresholds for TieredCognitionBackend (策略 D). Pure, no model."""
    escalate_below_confidence: float = 0.6  # fast confidence below this -> escalate to deep
    critical_always_deep: bool = True       # L1-critical -> prefer deep when online
    escalate_if_fast_critical: bool = True  # fast itself says critical -> escalate to deep


def tier_policy_from_dict(cfg: Optional[dict]) -> TierPolicy:
    spec = cfg or {}
    return TierPolicy(
        escalate_below_confidence=float(spec.get("escalate_below_confidence", 0.6)),
        critical_always_deep=bool(spec.get("critical_always_deep", True)),
        escalate_if_fast_critical=bool(spec.get("escalate_if_fast_critical", True)),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_tiered_cognition -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/cognition.py tests/test_tiered_cognition.py
git commit -m "feat(inspection): TierPolicy for L1.5 tiered cognition

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `TieredCognitionBackend` (policy D + 3-tier degradation)

**Files:**
- Modify: `rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/cognition.py` (add after `make_backend`)
- Test: `tests/test_tiered_cognition.py` (append a new test class + a fake backend)

**Interfaces:**
- Consumes: `TierPolicy` (Task 1), `MockCognitionBackend`, `CognitionResult`, `CognitionRequest` (existing).
- Produces:
  - `class TieredCognitionBackend` with `__init__(self, fast, deep=None, fallback=None, policy=None)` and `assess(self, request) -> CognitionResult`.
  - Module constant `_TIER_OFFLINE_ERRORS` (exception tuple) — internal.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tiered_cognition.py` (add the imports at the top alongside the existing import line, and the new classes at the end before `if __name__`):

```python
import urllib.error  # add near top with the other imports

from inspection_manager.cognition import (  # extend the existing import block
    CognitionRequest,
    CognitionResult,
    TieredCognitionBackend,
)
from inspection_manager.events import HazardEvent  # noqa: E402


def _event(severity="warning"):
    return HazardEvent(
        event_id="e1", timestamp="2026-06-17T10:00:00+08:00", station_id="desk-03",
        source="thermal", event_type="thermal_risk", severity=severity,
        confidence=0.8, summary="检测到电烙铁",
    )


def _result(sev="warning", conf=0.9, reason="x"):
    return CognitionResult(
        explanation="e", confirmed_severity=sev, suggested_actions=["log"],
        escalate_to_cloud=False, confidence=conf, reason=reason,
    )


class FakeBackend:
    """Injectable CognitionBackend: returns a fixed result, or raises, and counts calls."""
    def __init__(self, result=None, raises=None):
        self.result = result
        self.raises = raises
        self.calls = 0

    def assess(self, request):
        self.calls += 1
        if self.raises is not None:
            raise self.raises
        return self.result


class TieredAssessTests(unittest.TestCase):
    def _req(self, severity="warning"):
        return CognitionRequest(event=_event(severity))

    def test_critical_uses_deep_when_online_and_skips_fast(self):
        fast = FakeBackend(_result(reason="fast"))
        deep = FakeBackend(_result(reason="deep"))
        b = TieredCognitionBackend(fast=fast, deep=deep)
        out = b.assess(self._req("critical"))
        self.assertEqual(out.reason, "deep")
        self.assertEqual(deep.calls, 1)
        self.assertEqual(fast.calls, 0)  # deep online -> fast not run

    def test_critical_falls_back_to_fast_when_deep_offline(self):
        fast = FakeBackend(_result(reason="fast"))
        deep = FakeBackend(raises=urllib.error.URLError("offline"))
        b = TieredCognitionBackend(fast=fast, deep=deep)
        out = b.assess(self._req("critical"))
        self.assertEqual(fast.calls, 1)
        self.assertIn("L2 offline", out.reason)

    def test_noncritical_confident_uses_only_fast(self):
        fast = FakeBackend(_result(conf=0.95, reason="fast"))
        deep = FakeBackend(_result(reason="deep"))
        b = TieredCognitionBackend(fast=fast, deep=deep)
        out = b.assess(self._req("warning"))
        self.assertEqual(out.reason, "fast")
        self.assertEqual(deep.calls, 0)  # confident -> no escalation

    def test_noncritical_uncertain_escalates_to_deep(self):
        fast = FakeBackend(_result(conf=0.3, reason="fast"))
        deep = FakeBackend(_result(reason="deep"))
        b = TieredCognitionBackend(fast=fast, deep=deep)
        out = b.assess(self._req("warning"))
        self.assertEqual(out.reason, "deep")
        self.assertEqual(deep.calls, 1)

    def test_noncritical_uncertain_deep_offline_keeps_fast(self):
        fast = FakeBackend(_result(conf=0.3, reason="fast"))
        deep = FakeBackend(raises=urllib.error.URLError("offline"))
        b = TieredCognitionBackend(fast=fast, deep=deep)
        out = b.assess(self._req("warning"))
        self.assertIn("L2 offline", out.reason)

    def test_escalate_if_fast_says_critical(self):
        fast = FakeBackend(_result(sev="critical", conf=0.95, reason="fast"))
        deep = FakeBackend(_result(reason="deep"))
        b = TieredCognitionBackend(fast=fast, deep=deep)
        out = b.assess(self._req("warning"))  # L1 said warning; fast upgraded to critical
        self.assertEqual(out.reason, "deep")
        self.assertEqual(deep.calls, 1)

    def test_fast_failure_degrades_to_rules_fallback(self):
        fast = FakeBackend(raises=RuntimeError("model down"))
        fallback = FakeBackend(_result(reason="rules"))
        b = TieredCognitionBackend(fast=fast, deep=None, fallback=fallback)
        out = b.assess(self._req("warning"))
        self.assertEqual(fallback.calls, 1)
        self.assertIn("rules", out.reason)

    def test_no_deep_configured_uses_fast_even_for_critical(self):
        fast = FakeBackend(_result(reason="fast"))
        b = TieredCognitionBackend(fast=fast, deep=None)
        out = b.assess(self._req("critical"))
        self.assertEqual(out.reason, "fast")

    def test_default_fallback_is_mock(self):
        fast = FakeBackend(raises=RuntimeError("down"))
        b = TieredCognitionBackend(fast=fast)  # no fallback -> MockCognitionBackend
        out = b.assess(self._req("warning"))  # must still return a result, not raise
        self.assertIsInstance(out, CognitionResult)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_tiered_cognition -v`
Expected: FAIL — `ImportError: cannot import name 'TieredCognitionBackend'`.

- [ ] **Step 3: Write minimal implementation**

In `cognition.py`, add `import socket` and `import urllib.error` at the top (with the existing `import json`), then add after `make_backend`:

```python
# Errors from a deep (LAN/cloud) backend that mean "unreachable" -> degrade to fast.
_TIER_OFFLINE_ERRORS = (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError)


class TieredCognitionBackend:
    """Compose fast (L1.5 local VLM) + deep (L2 7B) + rules fallback (策略 D).

    Drop-in CognitionBackend. fast/deep are normally LocalVLMBackend instances that
    differ only by base_url. Branches:
      * L1-critical & critical_always_deep & deep present -> try deep, else fast.
      * otherwise -> fast first; escalate to deep only if fast is uncertain (low
        confidence) or fast itself判 critical. If deep unreachable, keep fast.
    fast failure degrades to the rules fallback so assess() never raises.
    """

    def __init__(self, fast, deep=None, fallback=None, policy: Optional[TierPolicy] = None) -> None:
        self.fast = fast
        self.deep = deep
        self.fallback = fallback or MockCognitionBackend()
        self.policy = policy or TierPolicy()

    def assess(self, request: CognitionRequest) -> CognitionResult:
        critical = getattr(request.event, "severity", "") == "critical"

        if critical and self.policy.critical_always_deep and self.deep is not None:
            deep_result = self._try_deep(request)
            if deep_result is not None:
                return deep_result
            result, from_rules = self._fast(request)
            if not from_rules:
                result.reason = "L1.5 (L2 offline, L1-critical)"
            return result

        result, from_rules = self._fast(request)
        if from_rules:
            return result
        if self.deep is not None and self._should_escalate(result):
            deep_result = self._try_deep(request)
            if deep_result is not None:
                return deep_result
            result.reason = "L1.5 (uncertain, L2 offline)"
        return result

    def _should_escalate(self, fast_result: CognitionResult) -> bool:
        if fast_result.confidence < self.policy.escalate_below_confidence:
            return True
        if self.policy.escalate_if_fast_critical and fast_result.confirmed_severity == "critical":
            return True
        return False

    def _try_deep(self, request: CognitionRequest) -> Optional[CognitionResult]:
        try:
            return self.deep.assess(request)
        except _TIER_OFFLINE_ERRORS:
            return None

    def _fast(self, request: CognitionRequest):
        """Return (result, from_rules). fast failure -> rules fallback (never raises)."""
        try:
            return self.fast.assess(request), False
        except Exception:  # noqa: BLE001 - local model down -> rules fallback
            r = self.fallback.assess(request)
            r.reason = "rules fallback (L1.5 unavailable)"
            return r, True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_tiered_cognition -v`
Expected: PASS (3 from Task 1 + 9 here = 12).

- [ ] **Step 5: Commit**

```bash
git add rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/cognition.py tests/test_tiered_cognition.py
git commit -m "feat(inspection): TieredCognitionBackend (policy D + 3-tier degradation)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Config reading — `tier_settings_from_dict` + `cognition.yaml`

**Files:**
- Modify: `rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/config.py` (add a reader)
- Modify: `rdk_x5/ros2_ws/src/inspection_manager/config/cognition.yaml` (add a `tier:` section + backend comment)
- Test: `tests/test_tiered_cognition.py` (append)

**Interfaces:**
- Consumes: `tier_policy_from_dict` from `.cognition` (Task 1).
- Produces: `tier_settings_from_dict(cfg: dict) -> dict` with keys `fast_model, fast_base_url, deep_model, deep_base_url, policy` (`policy` is a `TierPolicy`). Empty `deep_base_url` means "no deep backend".

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tiered_cognition.py` (add the import to the top import area and a new test class at the end):

```python
from inspection_manager.config import tier_settings_from_dict  # noqa: E402


class TierSettingsTests(unittest.TestCase):
    def test_reads_fast_deep_and_policy(self):
        cfg = {
            "backend": "tiered",
            "tier": {
                "fast": {"vlm_model": "qwen2-vl:2b", "vlm_base_url": "http://localhost:8080/v1"},
                "deep": {"vlm_model": "qwen2.5vl:7b", "vlm_base_url": "http://192.168.128.100:11434/v1"},
                "policy": {"escalate_below_confidence": 0.5},
            },
        }
        s = tier_settings_from_dict(cfg)
        self.assertEqual(s["fast_model"], "qwen2-vl:2b")
        self.assertEqual(s["fast_base_url"], "http://localhost:8080/v1")
        self.assertEqual(s["deep_base_url"], "http://192.168.128.100:11434/v1")
        self.assertEqual(s["policy"].escalate_below_confidence, 0.5)

    def test_missing_deep_means_empty_base_url(self):
        s = tier_settings_from_dict({"tier": {"fast": {"vlm_model": "m"}}})
        self.assertEqual(s["deep_base_url"], "")  # -> node builds no deep backend

    def test_tolerates_empty_cfg(self):
        s = tier_settings_from_dict({})
        self.assertIn("fast_base_url", s)
        self.assertEqual(s["deep_base_url"], "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_tiered_cognition -v`
Expected: FAIL — `ImportError: cannot import name 'tier_settings_from_dict'`.

- [ ] **Step 3: Write minimal implementation**

In `config.py`, add the import and reader (no circular import: `cognition.py` does not import `config.py`):

```python
from .cognition import tier_policy_from_dict  # add with the other top imports


def tier_settings_from_dict(cfg: dict) -> dict:
    """Read the 'tier' block of cognition.yaml -> fast/deep model+base_url + TierPolicy.

    Empty deep_base_url signals 'no deep backend' (the node then builds fast-only).
    """
    t = (cfg or {}).get("tier") or {}
    fast = t.get("fast") or {}
    deep = t.get("deep") or {}
    return {
        "fast_model": str(fast.get("vlm_model", "qwen2-vl:2b")),
        "fast_base_url": str(fast.get("vlm_base_url", "http://localhost:8080/v1")),
        "deep_model": str(deep.get("vlm_model", "qwen2.5vl:7b")),
        "deep_base_url": str(deep.get("vlm_base_url", "")),
        "policy": tier_policy_from_dict(t.get("policy") or {}),
    }
```

In `cognition.yaml`, change the backend comment line and append the tier block (keep `backend: mock` as the default). Replace the existing line:

```yaml
# backend: "mock" (rule/template, no model — default & demo-ready) | "local_vlm"
```

with:

```yaml
# backend: "mock" (rule/template — default) | "local_vlm" | "tiered" (L1.5 + L2 + rules)
```

and append at the end of the file:

```yaml

# tiered backend (L1.5 端侧小 VLM + L2 Mac 7B + 规则兜底). Used when backend: tiered.
# fast = RDK-local small VLM via llama-server/Ollama (OpenAI-compatible, localhost).
# deep = Mac 7B; leave vlm_base_url empty to disable deep (fast-only / no escalation).
tier:
  fast:
    vlm_model: "qwen2-vl:2b"
    vlm_base_url: "http://localhost:8080/v1"
  deep:
    vlm_model: "qwen2.5vl:7b"
    vlm_base_url: ""        # e.g. http://192.168.128.100:11434/v1 (Mac); empty -> no deep
  policy:
    escalate_below_confidence: 0.6
    critical_always_deep: true
    escalate_if_fast_critical: true
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_tiered_cognition -v`
Expected: PASS (15 total).

- [ ] **Step 5: Commit**

```bash
git add rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/config.py rdk_x5/ros2_ws/src/inspection_manager/config/cognition.yaml tests/test_tiered_cognition.py
git commit -m "feat(inspection): tier_settings_from_dict + cognition.yaml tier block

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Wire `backend: tiered` into `cognition_node`

**Files:**
- Modify: `rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/cognition_node.py` (`_build_backend`)

**Interfaces:**
- Consumes: `tier_settings_from_dict` (Task 3), `TieredCognitionBackend`/`LocalVLMBackend`/`MockCognitionBackend` (Tasks 1–2 / existing), `ollama_vlm_client` (existing).
- Produces: nothing new for later tasks; `cognition_node` selects the tiered backend when `cognition.yaml` has `backend: tiered`.

Note: `cognition_node` imports rclpy, so it is **not** unit-tested off-board (matches the repo). Verify with an AST syntax check + the existing full suite (no regression).

- [ ] **Step 1: Add the tiered branch**

In `cognition_node.py`, the current `_build_backend` is:

```python
    def _build_backend(self, name: str, cfg: dict):
        if name == "local_vlm":
            from inspection_manager.qwen_client import ollama_vlm_client

            client = ollama_vlm_client(
                model=str(cfg.get("vlm_model", "qwen2.5vl:7b")),
                base_url=str(cfg.get("vlm_base_url", "http://localhost:11434/v1")),
            )
            return make_backend("local_vlm", policy=self.policy, client=client)
        return make_backend(name, policy=self.policy)
```

Replace it with (adds the `tiered` branch; leaves `local_vlm` and the default unchanged):

```python
    def _build_backend(self, name: str, cfg: dict):
        if name == "local_vlm":
            from inspection_manager.qwen_client import ollama_vlm_client

            client = ollama_vlm_client(
                model=str(cfg.get("vlm_model", "qwen2.5vl:7b")),
                base_url=str(cfg.get("vlm_base_url", "http://localhost:11434/v1")),
            )
            return make_backend("local_vlm", policy=self.policy, client=client)
        if name == "tiered":
            from inspection_manager.qwen_client import ollama_vlm_client
            from inspection_manager.config import tier_settings_from_dict
            from inspection_manager.cognition import (
                LocalVLMBackend,
                MockCognitionBackend,
                TieredCognitionBackend,
            )

            ts = tier_settings_from_dict(cfg)
            fast = LocalVLMBackend(
                client=ollama_vlm_client(model=ts["fast_model"], base_url=ts["fast_base_url"]),
                policy=self.policy,
            )
            deep = None
            if ts["deep_base_url"]:
                deep = LocalVLMBackend(
                    client=ollama_vlm_client(model=ts["deep_model"], base_url=ts["deep_base_url"]),
                    policy=self.policy,
                )
            return TieredCognitionBackend(
                fast=fast, deep=deep, fallback=MockCognitionBackend(self.policy), policy=ts["policy"]
            )
        return make_backend(name, policy=self.policy)
```

- [ ] **Step 2: Syntax-check the node (no ROS needed)**

Run: `python3 -c "import ast; ast.parse(open('rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/cognition_node.py').read()); print('cognition_node OK')"`
Expected: prints `cognition_node OK`.

- [ ] **Step 3: Run the full suite (no regression)**

Run: `python3 -m unittest discover -s tests`
Expected: `OK` (existing tests + the new tiered tests all pass).

- [ ] **Step 4: Commit**

```bash
git add rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/cognition_node.py
git commit -m "feat(inspection): cognition_node selects tiered backend (backend: tiered)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Offline degradation demo script

**Files:**
- Create: `rdk_x5/scripts/tiered_cognition_demo.py`

**Interfaces:**
- Consumes: `TieredCognitionBackend`, `TierPolicy`, `CognitionRequest`, `CognitionResult` (Tasks 1–2), `HazardEvent` (existing). No ROS, no model — uses inline fakes to simulate fast/deep online/offline/confident/uncertain.
- Produces: a runnable script printing which tier handled each sample event + the reason. (Not imported by other code; manual verification artifact.)

- [ ] **Step 1: Write the demo script**

Create `rdk_x5/scripts/tiered_cognition_demo.py`:

```python
#!/usr/bin/env python3
"""Offline demo of L1.5 TieredCognitionBackend — no model, no ROS.

Feeds sample events through the real TieredCognitionBackend with FAKE fast/deep
backends to show the 3-tier degradation (deep -> fast -> rules) and policy D.

Run: python3 rdk_x5/scripts/tiered_cognition_demo.py
"""
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "ros2_ws" / "src" / "inspection_manager"
sys.path.insert(0, str(PKG))

import urllib.error  # noqa: E402

from inspection_manager.cognition import (  # noqa: E402
    CognitionRequest,
    CognitionResult,
    TieredCognitionBackend,
    TierPolicy,
)
from inspection_manager.events import HazardEvent  # noqa: E402


class Fake:
    def __init__(self, result=None, raises=None):
        self.result, self.raises = result, raises

    def assess(self, request):
        if self.raises is not None:
            raise self.raises
        return self.result


def event(severity, summary):
    return HazardEvent(
        event_id="e", timestamp="2026-06-17T10:00:00+08:00", station_id="desk-03",
        source="thermal", event_type="thermal_risk", severity=severity,
        confidence=0.8, summary=summary,
    )


def result(sev, conf, reason):
    return CognitionResult(
        explanation=f"[{reason}] {sev}", confirmed_severity=sev, suggested_actions=["log"],
        escalate_to_cloud=False, confidence=conf, reason=reason,
    )


def show(title, backend, ev):
    out = backend.assess(CognitionRequest(event=ev))
    print(f"  {title:32s} -> severity={out.confirmed_severity:8s} reason={out.reason}")


def main():
    deep_ok = Fake(result("critical", 0.95, "deep(7B)"))
    deep_off = Fake(raises=urllib.error.URLError("offline"))
    fast_sure = Fake(result("warning", 0.95, "fast(L1.5)"))
    fast_unsure = Fake(result("warning", 0.3, "fast(L1.5)"))
    fast_down = Fake(raises=RuntimeError("model down"))
    policy = TierPolicy()

    print("L1.5 tiered cognition — 3-tier degradation demo\n")
    print("[critical event]")
    show("deep online", TieredCognitionBackend(fast_sure, deep_ok, policy=policy), event("critical", "电烙铁145C"))
    show("deep OFFLINE -> fast", TieredCognitionBackend(fast_sure, deep_off, policy=policy), event("critical", "电烙铁145C"))
    print("\n[warning event]")
    show("fast confident -> local only", TieredCognitionBackend(fast_sure, deep_ok, policy=policy), event("warning", "插排"))
    show("fast unsure -> deep", TieredCognitionBackend(fast_unsure, deep_ok, policy=policy), event("warning", "插排"))
    show("fast unsure + deep OFFLINE", TieredCognitionBackend(fast_unsure, deep_off, policy=policy), event("warning", "插排"))
    show("fast DOWN -> rules fallback", TieredCognitionBackend(fast_down, deep_ok, policy=policy), event("warning", "插排"))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the demo**

Run: `python3 rdk_x5/scripts/tiered_cognition_demo.py`
Expected: 6 lines; reasons show `deep(7B)` when online, `L1.5 (L2 offline...)` when deep off, `fast(L1.5)` when confident, and `rules fallback (L1.5 unavailable)` when fast down. No traceback.

- [ ] **Step 3: Commit**

```bash
git add rdk_x5/scripts/tiered_cognition_demo.py
git commit -m "feat(inspection): offline demo for tiered cognition degradation

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final Verification

- [ ] Run `python3 -m unittest discover -s tests` — expect `OK`, ~15 new tiered tests + no regression on existing (~223 → ~238).
- [ ] Run `python3 rdk_x5/scripts/tiered_cognition_demo.py` — expect the 6-line degradation table, no traceback.
- [ ] Confirm no edits leaked into `actions.py`, `escalation.py`, `report*.py`, or `CognitionRequest`/`CognitionResult` fields.

## Deferred (on-board, NOT in this plan)

- RDK-local small VLM runtime: `llama-server` (llama.cpp, OpenAI-compatible) serving a small VLM; set `tier.fast.vlm_base_url` to its localhost URL; set `tier.deep.vlm_base_url` to the Mac.
- Pick + quantize the actual small VLM (CPU/llama.cpp first, then evaluate BPU/OpenExplorer).
- Tune `escalate_below_confidence` and the policy on real hardware.
