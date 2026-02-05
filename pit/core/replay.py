"""Core replay logic for time-travel across versions."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any


@dataclass
class ReplayResult:
    """Result of replaying input on a specific version."""
    version_number: int
    input_text: str
    output: Optional[str]
    latency_ms: Optional[float]
    token_usage: Optional[int]
    error: Optional[str]
    cached: bool

    def to_dict(self) -> dict:
        return {
            "version_number": self.version_number,
            "input_text": self.input_text,
            "output": self.output,
            "latency_ms": self.latency_ms,
            "token_usage": self.token_usage,
            "error": self.error,
            "cached": self.cached,
        }


class ReplayCache:
    """Caches replay results to avoid redundant LLM calls."""

    CACHE_DIR = "replay_cache"

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.cache_dir = project_root / ".pit" / self.CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_key(self, prompt_name: str, version: int, input_text: str) -> str:
        """Generate a cache key for a replay."""
        content = f"{prompt_name}:{version}:{input_text}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _get_cache_path(self, key: str) -> Path:
        """Get the cache file path for a key."""
        return self.cache_dir / f"{key}.json"

    def get(self, prompt_name: str, version: int, input_text: str) -> Optional[ReplayResult]:
        """Get cached result if available."""
        key = self._get_cache_key(prompt_name, version, input_text)
        cache_path = self._get_cache_path(key)

        if not cache_path.exists():
            return None

        try:
            data = json.loads(cache_path.read_text())
            return ReplayResult(
                version_number=data["version_number"],
                input_text=data["input_text"],
                output=data.get("output"),
                latency_ms=data.get("latency_ms"),
                token_usage=data.get("token_usage"),
                error=data.get("error"),
                cached=True,
            )
        except (json.JSONDecodeError, KeyError):
            return None

    def set(self, prompt_name: str, version: int, result: ReplayResult) -> None:
        """Cache a replay result."""
        key = self._get_cache_key(prompt_name, version, result.input_text)
        cache_path = self._get_cache_path(key)

        cache_path.write_text(json.dumps(result.to_dict(), indent=2))

    def clear(self) -> int:
        """Clear all cached results. Returns number of files deleted."""
        count = 0
        for cache_file in self.cache_dir.glob("*.json"):
            cache_file.unlink()
            count += 1
        return count


class ReplayEngine:
    """Engine for replaying inputs across versions."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.cache = ReplayCache(project_root)

    def replay(
        self,
        prompt_name: str,
        versions: List[int],
        input_text: str,
        use_cache: bool = True,
        provider: Optional[Any] = None,
    ) -> List[ReplayResult]:
        """Replay input across multiple versions.

        Args:
            prompt_name: Name of the prompt
            versions: List of version numbers to test
            input_text: Input to send to each version
            use_cache: Whether to use cached results
            provider: Optional LLM provider for execution

        Returns:
            List of replay results
        """
        from pit.db.database import get_session
        from pit.db.repository import PromptRepository, VersionRepository

        results = []

        with get_session(self.project_root) as session:
            prompt_repo = PromptRepository(session)
            version_repo = VersionRepository(session)

            prompt = prompt_repo.get_by_name(prompt_name)
            if not prompt:
                raise ValueError(f"Prompt '{prompt_name}' not found")

            for version_num in versions:
                # Check cache first
                if use_cache:
                    cached = self.cache.get(prompt_name, version_num, input_text)
                    if cached:
                        results.append(cached)
                        continue

                # Get version content
                version = version_repo.get_by_number(prompt.id, version_num)
                if not version:
                    result = ReplayResult(
                        version_number=version_num,
                        input_text=input_text,
                        output=None,
                        latency_ms=None,
                        token_usage=None,
                        error=f"Version v{version_num} not found",
                        cached=False,
                    )
                    results.append(result)
                    continue

                # Execute if provider is available
                if provider:
                    result = self._execute_with_provider(
                        version.content, input_text, version_num, provider
                    )
                    if use_cache:
                        self.cache.set(prompt_name, version_num, result)
                    results.append(result)
                else:
                    # Return result without execution
                    result = ReplayResult(
                        version_number=version_num,
                        input_text=input_text,
                        output=None,
                        latency_ms=None,
                        token_usage=None,
                        error="No LLM provider configured",
                        cached=False,
                    )
                    results.append(result)

        return results

    def _execute_with_provider(
        self,
        prompt_content: str,
        input_text: str,
        version_num: int,
        provider: Any,
    ) -> ReplayResult:
        """Execute prompt with input using provider."""
        import time

        start_time = time.time()

        try:
            # This is a simplified placeholder
            # Real implementation would use the provider to send the prompt
            output = f"[Simulated output for version {version_num}]"
            latency_ms = (time.time() - start_time) * 1000

            return ReplayResult(
                version_number=version_num,
                input_text=input_text,
                output=output,
                latency_ms=latency_ms,
                token_usage=len(prompt_content.split()) + len(input_text.split()),
                error=None,
                cached=False,
            )
        except Exception as e:
            return ReplayResult(
                version_number=version_num,
                input_text=input_text,
                output=None,
                latency_ms=None,
                token_usage=None,
                error=str(e),
                cached=False,
            )

    def compare(
        self,
        prompt_name: str,
        versions: List[int],
        input_text: str,
    ) -> Dict[str, Any]:
        """Compare outputs across versions.

        Returns a comparison with statistics about differences.
        """
        results = self.replay(prompt_name, versions, input_text)

        comparison = {
            "input": input_text,
            "versions": versions,
            "results": [r.to_dict() for r in results],
            "statistics": {
                "total": len(results),
                "successful": sum(1 for r in results if r.error is None),
                "failed": sum(1 for r in results if r.error is not None),
                "cached": sum(1 for r in results if r.cached),
            },
        }

        # Calculate performance stats for successful results
        latencies = [r.latency_ms for r in results if r.latency_ms is not None]
        if latencies:
            comparison["statistics"]["avg_latency_ms"] = sum(latencies) / len(latencies)
            comparison["statistics"]["min_latency_ms"] = min(latencies)
            comparison["statistics"]["max_latency_ms"] = max(latencies)

        return comparison
