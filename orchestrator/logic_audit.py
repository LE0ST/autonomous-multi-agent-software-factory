"""Controller-owned logic audit and provider fallback implementation."""
from pathlib import Path
from orchestrator.state_manager import StateManager
from adapters import GeminiAdapter, DeepSeekAdapter, GLMAdapter, QwenAdapter, LogicAuditOutput, NetworkTransportError, sanitize_secret_text
from adapters.network_retry import is_transient_network_error
def create_security_adapter(provider: str, model: str, simulate: bool = False):
    """
    Factory creating a security logic audit adapter for supported providers.
    Supported: 'gemini', 'deepseek', 'qwen', 'glm'.
    Fails closed (raises ValueError) for unknown providers.
    """
    p = str(provider).lower().strip()
    if p == "gemini":
        client = GeminiAdapter(model=model)
    elif p == "deepseek":
        client = DeepSeekAdapter(model=model)
    elif p in ("qwen", "dashscope"):
        client = QwenAdapter(model=model)
    elif p in ("glm", "zhipu"):
        client = GLMAdapter(model=model)
    else:
        raise ValueError(
            f"Unsupported security logic audit provider: '{provider}'. "
            f"Supported providers are: 'gemini', 'deepseek', 'qwen', 'glm'."
        )

    if simulate:
        client.is_simulation = True
    return client

def execute_logic_security_audit(
    sm: StateManager,
    spec_path: Path,
    diff_output: str,
    sec_role: dict,
    simulate: bool = False,
    exit_process: bool = True
) -> tuple[bool, LogicAuditOutput | None, dict | None]:
    """
    Executes the Logic Security Audit with a strict, deterministic multi-provider fallback policy.

    Candidates:
      Primary: sec_role["provider"] / sec_role["model"]
      Fallbacks: sec_role.get("fallbacks", [])

    Rules:
      1. Sequential iteration over candidates starting with primary.
      2. Fallback ONLY on provider availability failures (NetworkTransportError, HTTP 429/502/503/504, timeout, connection).
      3. Never fall back on semantic FAIL (invariants violated): consumes security replan and stops.
      4. Never fall back on semantic UNCERTAIN / UNAVAILABLE status in LogicAuditOutput: requests human review and stops.
      5. Never fall back on JSON parsing or validation errors: halts human review and stops.
      6. On PASS: records audit_model_used and stops immediately.
      7. On exhaustion of all candidates by availability errors: requests human review and stops.
    """
    primary_provider = sec_role.get("provider", "gemini")
    primary_model = sec_role.get("model", "gemini-3.8-flash")
    candidates = [{"provider": primary_provider, "model": primary_model, "is_fallback": False}]

    for fb in sec_role.get("fallbacks", []):
        fb_prov = fb.get("provider")
        fb_mod = fb.get("model")
        if fb_prov and fb_mod:
            candidates.append({"provider": fb_prov, "model": fb_mod, "is_fallback": True})

    spec_content = spec_path.read_text(encoding="utf-8")
    availability_errors = []

    for candidate in candidates:
        provider = candidate["provider"]
        model = candidate["model"]
        is_fallback = candidate["is_fallback"]

        if is_fallback:
            msg = f"Falling back to Logic Security Auditor: {provider.upper()}:{model}..."
            print(f"[i] {msg}")
            sm.transition("LOGIC_AUDIT", msg)

        try:
            client = create_security_adapter(provider, model, simulate=simulate)
        except ValueError as e:
            clean_err = sanitize_secret_text(str(e))
            print(f"[!] Security adapter initialization failed: {clean_err}")
            sm.halt_human(f"Security adapter initialization failed: {clean_err}", exit_process=exit_process)
            return False, None, None

        try:
            audit_res = client.audit_logic_and_security(spec_content, diff_output)
        except NetworkTransportError as e:
            clean_err = sanitize_secret_text(str(e))
            code_info = f"HTTP {e.status_code}" if e.status_code else "transport/network"
            err_msg = f"{provider}:{model} unavailable ({code_info}): {clean_err}"
            print(f"[!] {err_msg}")
            availability_errors.append(err_msg)
            continue
        except Exception as e:
            is_retryable, reason, code, _ = is_transient_network_error(e)
            if is_retryable:
                clean_err = sanitize_secret_text(str(e))
                code_info = f"HTTP {code}" if code else "transport/network"
                err_msg = f"{provider}:{model} unavailable ({code_info}): {clean_err}"
                print(f"[!] {err_msg}")
                availability_errors.append(err_msg)
                continue

            clean_err = sanitize_secret_text(str(e))
            print(f"\n[!] Non-retryable error during logic security audit with {provider}:{model}: {clean_err}")
            sm.halt_human(
                f"Non-availability failure in Logic Security Audit ({provider}:{model}): {clean_err}",
                exit_process=exit_process
            )
            return False, None, None

        # Evaluates semantic verdicts
        if audit_res.status == "FAIL":
            print(f"[!] Logic audit failed under {provider}:{model}. Violated invariants: {audit_res.violated_invariants}")
            sm.consume_security_replan(f"Invariant violation ({provider}:{model}): {audit_res.justification}")
            return False, audit_res, None

        if audit_res.status in ("UNAVAILABLE", "UNCERTAIN"):
            print(f"[!] Inconclusive audit ({audit_res.status}) from {provider}:{model}: {audit_res.justification}")
            sm.request_human_review(
                reason=f"Inconclusive audit ({audit_res.status}) from {provider}:{model}: {audit_res.justification}",
                gate="LOGIC_AUDIT",
                exit_process=exit_process
            )
            return False, audit_res, None

        if audit_res.status == "SIMULATED":
            if not simulate:
                print(f"[!] CRITICAL ALERT: Received simulated audit from {provider}:{model} but pipeline is in live mode.")
                sm.halt_human(
                    f"Simulated audit received from {provider}:{model} in live run. Merge blocked.",
                    exit_process=exit_process
                )
                return False, None, None
            print(f"[i] Simulated audit (--simulate active) from {provider}:{model}. Proceeding.")

        model_info = {"provider": provider, "model": model}
        sm.record_audit_model(provider, model)
        print(f"\n[PASS] Logic security audit passed successfully using model: {model} ({provider.upper()})")
        return True, audit_res, model_info

    summary_details = " | ".join(availability_errors)
    print(f"\n[!] All configured Logic Security audit models ({len(candidates)} attempted) failed due to availability errors.")
    sm.request_human_review(
        reason=f"All logic security audit models unavailable after retries ({len(candidates)} model(s) attempted). Details: {summary_details}",
        gate="LOGIC_AUDIT",
        exit_process=exit_process
    )
    return False, None, None
