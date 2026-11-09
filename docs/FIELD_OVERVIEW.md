# Optional field overview

Refs #24. The field-overview button opens an additive local read display;
reload retains the classic layout. Existing mode/network/power controls and
confirmations stay in their original sections. No model or external service,
new request, extra SSE connection, privilege, firewall change or installer is
introduced. Web, TUI and e-paper mode contracts are unchanged.

Current mode comes only from state readback. Requested mode and request status
are separate; request acceptance is not a successful transition. A fresh state
matching the requested target is labelled observed, not an enforcement receipt.
Failed/unavailable requests remain visible. NAT is a configuration report, not
proof that the protected client can reach a service. WARNING is a display
condition and never becomes a mode. Missing sensor/connection data stays unknown.

Snapshot time is required for freshness: future/missing time is unknown, age
above ten seconds is stale, and failed state retrieval is offline. The one-shot
expiry timer ages a frozen snapshot without making requests. Recent events reuse
the existing deduplicated notification stream; at most 24 page-local entries
are retained, prioritized error/warning/other. Their count is not an incident
total. Text and details are bounded and inserted as text, never HTML. Missing
stream/data is explicit; no historical trend is manufactured.

English/Japanese section labels, keyboard controls, 44px targets and a narrow
single-column layout are provided. Software and synthetic browser checks do not
prove operator usefulness, Zero 2 W performance or hardware/network acceptance.
Asset/render/resource baseline measurements and counterbalanced held-out task
results in #24 remain required before a new layout default is selected.
