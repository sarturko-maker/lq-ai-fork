"""Deep-agent runtime for the fork's practice-area agents (ADR-F001/F002).

F0-S1 establishes the substrate: a thin factory around ``deepagents`` so the
pre-1.0 API churn is absorbed in one module, and a chat-model builder that
keeps the Inference Gateway as the only egress (gateway carries the provider
keys; agents authenticate with the shared gateway key header).
"""

from app.agents.factory import (
    build_deep_agent,
    build_gateway_chat_model,
    build_gateway_http_client,
)

__all__ = ["build_deep_agent", "build_gateway_chat_model", "build_gateway_http_client"]
