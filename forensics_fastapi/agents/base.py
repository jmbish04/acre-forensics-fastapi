from ..forensics.remote_worker_api import RemoteWorkerClient


class BaseAgentClient:
    def __init__(self, agent_type: str, engagement_id: str = "default"):
        self.client = RemoteWorkerClient()
        self.agent_type = agent_type
        self.engagement_id = engagement_id

    def _invoke(self, action: str, payload: dict) -> dict:
        """
        Invokes the remote Worker Agent and logs the attempt and result.
        """
        # 1. Trace Start
        self.client.log_event(
            type="INFO",
            workflow_id=self.engagement_id,
            step_name=f"{self.agent_type}.{action}",
            message=f"Invoking Agent Action: {action}",
            action_type="AGENT_CALL",
            metadata={
                "payload_summary": list(payload.keys())
            },  # Don't log full payload if sensitive
        )

        try:
            # 2. Call Worker API (Matches the generic protocol in internal.ts)
            # internal.ts expects: agentName (Enum), agentId, action, payload

            # Map simplified names to Worker Bindings
            agent_map = {
                "classifier": "CLASSIFIER_AGENT",
                "forensic": "FORENSICS_AGENT",
                "rag": "RAG_AGENT",
                "strategy": "STRATEGY_AGENT",  # If generic agent used
            }
            worker_agent_name = agent_map.get(self.agent_type, self.agent_type.upper())

            # Use generic run_agent helper from RemoteWorkerClient
            response = self.client.run_agent(
                agent_name=worker_agent_name,
                action=action,
                payload=payload,
                agent_id=self.engagement_id,
            )

            # 3. Trace Success
            self.client.log_event(
                type="INFO",
                workflow_id=self.engagement_id,
                step_name=f"{self.agent_type}.{action}",
                message="Agent Action Complete",
                action_type="AGENT_RESULT",
                metadata={"status": "success"},
            )

            # Result is already unpacked by run_agent usually, but check
            # internal.ts /agent/run returns { result: data }
            # RemoteWorkerClient.run_agent returns resp.get("result")
            return response

        except Exception as e:
            # 4. Trace Failure
            self.client.log_event(
                type="ERROR",
                workflow_id=self.engagement_id,
                step_name=f"{self.agent_type}.{action}",
                message=str(e),
                error_type="AGENT_FAILURE",
            )
            raise e
