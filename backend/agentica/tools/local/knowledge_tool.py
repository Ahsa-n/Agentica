"""Knowledge base search tool."""

from __future__ import annotations

from pydantic import BaseModel, Field

from agentica.tools.base import BaseTarget, BaseTool, RiskTier, ToolCategory, ToolSpec
from agentica.tools.registry import registry


class SearchKBInput(BaseModel):
    query: str = Field(..., description="Natural-language question to search the knowledge base")
    top_k: int = Field(default=5, ge=1, le=20)
    model_config = {"extra": "forbid"}


class KBChunkResult(BaseModel):
    document: str
    heading_path: str | None
    content: str
    score: float
    model_config = {"extra": "forbid"}


class SearchKBResult(BaseModel):
    query: str
    results: list[KBChunkResult]
    found: bool
    model_config = {"extra": "forbid"}


class SearchKnowledgeBase(BaseTool[SearchKBInput, SearchKBResult]):
    spec = ToolSpec(
        name="search_knowledge_base",
        description=(
            "Search the organisation's knowledge base (SOPs, runbooks, procedures). "
            "Returns relevant chunks with citations. "
            "Returns 'not found' when no relevant content exists — never invents procedures."
        ),
        category=ToolCategory.KNOWLEDGE,
        risk_tier=RiskTier.READ,
        input_schema=SearchKBInput.model_json_schema(),
    )

    async def run(self, args: SearchKBInput, target: BaseTarget | None = None) -> SearchKBResult:
        from agentica.rag.search import hybrid_search
        results = await hybrid_search(args.query, top_k=args.top_k)
        return SearchKBResult(
            query=args.query,
            results=results,
            found=bool(results),
        )


registry.register(SearchKnowledgeBase())
