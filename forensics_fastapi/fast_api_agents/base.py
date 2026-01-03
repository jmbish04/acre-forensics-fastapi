from typing import Any

from ..forensics.remote_worker_api import RemoteWorkerClient


class BaseAgentClient:
    def __init__(self, agent_type: str, engagement_id: str = "default"):
        self.client = RemoteWorkerClient()
        self.agent_type = agent_type
        self.engagement_id = engagement_id

    def _invoke(self, action: str, payload: dict) -> Any:
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
            metadata={"payload_keys": list(payload.keys())},
        )

        try:
            # 2. Map local alias to Worker Binding Name (Manifest ID or Binding)
            agent_map = {
                # Workflow Agents
                "engagement_orchestrator": "ENGAGEMENT_ORCHESTRATOR",
                "verification": "VERIFICATION_AGENT",
                "strategy": "STRATEGY_AGENT",
                "classifier": "CLASSIFIER_AGENT",
                "forensic": "FORENSICS_AGENT",
                
                # Team Agents
                "forensic_team": "FORENSIC_ORCHESTRATOR",
                "judge": "AGENT_JUDGE",
                "profiler": "AGENT_PROFILER",
                "timeline": "AGENT_TIMELINE",

                # IT & Tools
                "geeksquad": "IT_AGENT", # Note: Check binding in manifest, usually inferred or custom
                "rag": "RAG_AGENT",
                "terminal": "TERMINAL_AGENT"
            }
            
            # Default to uppercase if not found in map
            worker_agent_name = agent_map.get(self.agent_type, self.agent_type.upper())

            # 3. Call Generic RPC
            response = self.client.run_agent(
                agent_name=worker_agent_name,
                action=action,
                payload=payload,
                agent_id=self.engagement_id,
            )

            # 4. Trace Success
            self.client.log_event(
                type="INFO",
                workflow_id=self.engagement_id,
                step_name=f"{self.agent_type}.{action}",
                message="Agent Action Complete",
                action_type="AGENT_RESULT",
                metadata={"status": "success"},
            )
            return response

        except Exception as e:
            self.client.log_event(
                type="ERROR",
                workflow_id=self.engagement_id,
                step_name=f"{self.agent_type}.{action}",
                message=str(e),
                error_type="AGENT_FAILURE",
            )
            raise e
