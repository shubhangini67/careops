import contextvars
from abc import ABC, abstractmethod
from threading import Lock

# Tags usage records with the LangGraph node currently making the call, scoped
# per-asyncio-task (each parallel fan-out node runs as its own Task, so this
# does not leak across concurrently running nodes that share a provider tier).
# Without this, two parallel nodes sharing a provider (e.g. reservation and
# inventory both on the "fast" tier) can steal each other's usage records when
# _inject() drains the shared buffer at node start/end — corrupting per-node
# cost/token attribution in the observability traces.
_current_node: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "llm_usage_node", default=None
)


def bind_llm_usage_node(node: str | None) -> contextvars.Token:
    """Tag subsequent record_usage() calls on this asyncio task with `node`."""
    return _current_node.set(node)


def reset_llm_usage_node(token: contextvars.Token) -> None:
    _current_node.reset(token)


# Approximate cost rates per 1M tokens (USD) — update as pricing changes
_COST_PER_1M = {
    "gemini-2.5-flash":        {"input": 0.075, "output": 0.30},
    "llama-3.3-70b-versatile": {"input": 0.59,  "output": 0.79},
    "deepseek-v4-flash":       {"input": 0.12,  "output": 0.24},   # via CometAPI
    "deepseek-v4-pro":         {"input": 0.416, "output": 0.832},  # via CometAPI
    "gemini-3.5-flash":        {"input": 1.20,  "output": 7.20},   # via CometAPI
    "claude-sonnet-4-6":       {"input": 2.40,  "output": 12.00},  # via CometAPI
}


def _calc_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    rates = _COST_PER_1M.get(model, {"input": 0.0, "output": 0.0})
    return round(
        (prompt_tokens  / 1_000_000) * rates["input"] +
        (completion_tokens / 1_000_000) * rates["output"],
        6,
    )


class BaseLLMProvider(ABC):
    """Abstract base for all LLM providers.
    Agents always depend on this interface — never on a concrete provider.
    """

    def __init__(self) -> None:
        self._usage_records: list[dict] = []
        self._lock = Lock()
        self.provider_name = self.__class__.__name__.removesuffix("Provider").lower()
        self.model = "unknown"

    def record_usage(self, model: str, prompt_tokens: int, completion_tokens: int) -> None:
        """Called by concrete providers after every LLM call."""
        record = {
            "provider": self.provider_name,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cost_usd": _calc_cost(model, prompt_tokens, completion_tokens),
            "node": _current_node.get(),
        }
        with self._lock:
            self._usage_records.append(record)

    def _trace_generation(
        self,
        *,
        prompt: str,
        system_prompt: str | None,
        output_text: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None:
        """Emit a Langfuse generation observation nested under the current node span.

        Best-effort only — tracing must never break an LLM call. No-ops if
        Langfuse isn't configured (LANGFUSE_SECRET_KEY unset).
        """
        try:
            from app.core.settings import get_settings
            if not get_settings().langfuse_secret_key:
                return

            from langfuse import get_client
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            with get_client().start_as_current_observation(
                name=f"{self.provider_name}-completion",
                as_type="generation",
                input=messages,
                model=self.model,
                usage_details={"input": prompt_tokens, "output": completion_tokens},
            ) as gen:
                gen.update(output=output_text)
        except Exception:
            pass

    def drain_usage(self, node: str | None = None) -> list[dict]:
        """Return accumulated usage records and clear them.

        When `node` is given, only records tagged with that node (via
        bind_llm_usage_node) are drained — records belonging to other
        parallel-running nodes sharing this same provider instance are left
        untouched. When omitted, drains everything (safe for non-concurrent
        contexts, e.g. the final cleanup drain after a run completes).
        """
        with self._lock:
            if node is None:
                records = self._usage_records.copy()
                self._usage_records.clear()
            else:
                records = [r for r in self._usage_records if r.get("node") == node]
                self._usage_records = [r for r in self._usage_records if r.get("node") != node]
        return records

    @abstractmethod
    async def complete(
        self, prompt: str, system_prompt: str | None = None, temperature: float | None = None,
    ) -> str:
        """Send a prompt to the LLM and return the text response.

        `temperature` is optional and defaults to the provider/SDK's own
        default when omitted -- pass it explicitly only for calls that need
        low-variance output (e.g. a relevance classification), not narrative
        generation where the default is intentional.
        """

    @abstractmethod
    async def complete_json(
        self, prompt: str, system_prompt: str | None = None, temperature: float | None = None,
    ) -> dict:
        """Send a prompt and return a parsed JSON response."""
