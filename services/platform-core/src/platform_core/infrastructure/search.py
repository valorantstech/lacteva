"""Search infrastructure: OpenSearch client provider.

Foundation scope: connectivity + index-naming convention only.
TODO(M2): index lifecycle management (templates, mappings per module),
tenant-filtered search helpers, and an indexing consumer that projects
platform events into search indexes (CQRS read side).
"""

from functools import lru_cache

from platform_core.core.config import get_settings

INDEX_PREFIX = "lacteva"


def index_name(module: str) -> str:
    """Convention: lacteva-<module>, e.g. lacteva-audit."""
    return f"{INDEX_PREFIX}-{module}"


@lru_cache
def get_search_client():
    from opensearchpy import OpenSearch

    settings = get_settings()
    return OpenSearch(hosts=[settings.opensearch_url])
