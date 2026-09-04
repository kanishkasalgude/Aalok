"""
DOCUMENTED, NOT IMPLEMENTED extension point.

Razorpay publishes an official MCP server (github.com/razorpay/razorpay-mcp-server,
remote-hosted or local, 35+ tools spanning payments/orders/payment links/
refunds/QR/settlements/payouts). It is real, and architecturally it COULD
sit here as an alternate transport for PaymentProvider (see
integrations/razorpay/provider.py) instead of raw REST calls - e.g. a
future `RazorpayMCPProvider(PaymentProvider)` that calls MCP tools instead
of `requests.post(...)`.

It is NOT wired up in this project, for two reasons:
  1. It's real product surface Aalok doesn't need for an MVP that only
     ever needs Orders + Standard Checkout + webhook confirmation + refunds
     - all already implemented directly against the REST API.
  2. It is documented by Razorpay itself as a MERCHANT BACK-OFFICE
     automation surface (settlements, payouts, reconciliation) - if it were
     wired up, Aalok's own architecture requires it stay firmly behind
     PaymentService/RazorpayProvider, reachable only by Aalok's own
     deterministic order/payment logic. It must NEVER be exposed to the
     shopping LLM's tool layer (services/agent/tools.py) - that would
     reopen exactly the "LLM has a direct path to money" hole the whole
     Authorization/Policy boundary exists to close.

This class exists only so the extension point is visible in the codebase,
not to be constructed or called anywhere in this MVP.
"""
from __future__ import annotations


class RazorpayMCPProvider:
    """NOT IMPLEMENTED. Raises immediately if anything tries to construct
    it, rather than silently doing nothing."""

    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "RazorpayMCPProvider is a documented architectural extension point only - "
            "see this module's docstring and ARCHITECTURE.md 'Razorpay MCP extension point'. "
            "It is not implemented in this project and must not be exposed to the AI tool layer."
        )
