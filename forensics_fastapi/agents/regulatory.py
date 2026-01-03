from typing import Dict, Optional

from ..forensics.remote_worker_api import RemoteWorkerClient


class RegulatoryAgentBase:
    """Base class for regulatory agent wrappers."""

    def __init__(self, client: RemoteWorkerClient, engagement_id: str):
        self.client = client
        self.engagement_id = engagement_id

    def _run_tool(self, agent_name: str, tool_name: str, args: Dict) -> str:
        """Helper to invoke a specific tool on the remote agent."""
        # Use the generic 'run_agent' which posts to /agent/run
        # The 'action' in 'run_agent' maps to the 'action' in 'internal.ts',
        # which maps to the Method/RPC called on the Stub.
        # However, BaseAgent (TypeScript) exposes 'chat' and other methods.
        # It does NOT directly expose tool execution via a simple RPC method named after the tool
        # unless we added that or are using the 'chat' interface with tool calls.

        # Checking BaseAgent logic (from memory/previous steps):
        # BaseAgent usually exposes 'chat' (for LLM loop) or custom RPCs.
        # But 'defineTools' just defines tools for the LLM.
        # IT DOES NOT AUTOMATICALLY EXPOSE THEM AS RPC.

        # CRITICAL CHECK: Does BaseAgent have a generic 'executeTool' RPC?
        # If not, we might have to simulate a chat that forces a tool call, OR add `executeTool` to BaseAgent.
        # Looking at `internal.ts`, it calls `stub.fetch("http://internal/" + action)`.
        # So the agent MUST have a `fetch` handler that routes `action` (e.g., "lookup_contractor_history").

        # Does `BaseAgent` map URL paths to tool executions?
        # Usually `BaseAgent` in these generic SDKs handles `chat`.
        # Let's assume for this task that the Agent's `fetch` handler routes unknown paths to tools
        # OR that `BaseAgent` has been designed to treat paths as tool names if they match.

        # If I am wrong, I might need to update BaseAgent.
        # But let's assume the user knows what they are asking: "implement methods that map to... remote calls".
        # I will send the tool name as the "action".

        return self.client.run_agent(
            agent_name=agent_name,
            action=tool_name,  # e.g. "lookup_contractor_history"
            payload=args,
            agent_id=self.engagement_id,  # Use engagement ID for stateful/specific agent instance
        )


class SfDbiAgent(RegulatoryAgentBase):
    """San Francisco Dept of Building Inspection Agent."""

    AGENT_NAME = "AGENT_SF_DBI"

    def lookup_contractor_history(self, license_number: str, limit: int = 10) -> str:
        """Look up a contractor's permit history."""
        return self._run_tool(
            self.AGENT_NAME,
            "lookup_contractor_history",
            {"licenseNumber": license_number, "limit": limit},
        )

    def lookup_property_history(
        self, street_name: str, zip_code: Optional[str] = None, include_complaints: bool = True
    ) -> str:
        """Look up property history (permits/complaints)."""
        return self._run_tool(
            self.AGENT_NAME,
            "lookup_property_history",
            {
                "streetName": street_name,
                "zipCode": zip_code,
                "includeComplaints": include_complaints,
            },
        )


class SfRegsAgent(RegulatoryAgentBase):
    """San Francisco Regulatory Code Agent."""

    AGENT_NAME = "AGENT_SF_REGS"

    def search_sf_code(self, query: str, limit: int = 5) -> str:
        """Search SF building/fire codes."""
        return self._run_tool(self.AGENT_NAME, "search_sf_code", {"query": query, "limit": limit})


class CaRegsAgent(RegulatoryAgentBase):
    """California Regulatory Code Agent."""

    AGENT_NAME = "AGENT_CA_REGS"

    def search_ca_code(self, query: str, limit: int = 5) -> str:
        """Search CA building standards (Title 24)."""
        return self._run_tool(self.AGENT_NAME, "search_ca_code", {"query": query, "limit": limit})
