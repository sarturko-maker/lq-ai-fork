"""HTTP clients the backend API calls into (gateway, IdPs, etc.).

Currently only the Inference Gateway. Added here as a separate package so
that future external-service clients (OAuth providers, SCIM, etc.) live
alongside it with a consistent shape.
"""

from app.clients.gateway import GatewayClient, get_gateway_client

__all__ = ["GatewayClient", "get_gateway_client"]
