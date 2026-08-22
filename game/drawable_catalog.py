"""Load-once built-in drawable catalogue and bounded resolution cache."""

from __future__ import annotations

from collections import OrderedDict

from game.drawable_dsl import (
    DrawableCatalog,
    DrawableRenderContext,
    ResolvedDrawable,
    load_builtin_drawable_catalog,
    normalize_identifier,
    resolve_drawable,
)


DEFAULT_RESOLUTION_CACHE_LIMIT = 1024


def _context_signature(context: DrawableRenderContext) -> tuple:
    return (
        str(context.context),
        tuple(sorted((str(name), float(value)) for name, value in context.symbols.items())),
        tuple(
            sorted(
                (str(name), tuple(sorted(str(token) for token in tokens)))
                for name, tokens in context.conditions.items()
            )
        ),
    )


class RuntimeDrawableCatalog:
    """Own the immutable catalogue and reuse resolved geometry variants."""

    def __init__(self, *, cache_limit: int = DEFAULT_RESOLUTION_CACHE_LIMIT):
        self.cache_limit = max(1, int(cache_limit))
        self.catalog: DrawableCatalog = load_builtin_drawable_catalog()
        self._resolved: OrderedDict[tuple, ResolvedDrawable] = OrderedDict()

    @property
    def revision(self) -> str:
        return self.catalog.revision

    def reload(self) -> DrawableCatalog:
        self.catalog = load_builtin_drawable_catalog()
        self._resolved.clear()
        return self.catalog

    def resolve(
        self,
        drawable_id: str,
        context: DrawableRenderContext,
        *,
        variant: str = "compact",
    ) -> ResolvedDrawable:
        drawable_key = normalize_identifier(drawable_id)
        variant_key = normalize_identifier(variant) or "compact"
        cache_key = (
            self.catalog.revision,
            drawable_key,
            variant_key,
            _context_signature(context),
        )
        cached = self._resolved.get(cache_key)
        if cached is not None:
            self._resolved.move_to_end(cache_key)
            return cached
        resolved = resolve_drawable(
            self.catalog.require(drawable_key),
            context,
            variant=variant_key,
        )
        self._resolved[cache_key] = resolved
        self._resolved.move_to_end(cache_key)
        while len(self._resolved) > self.cache_limit:
            self._resolved.popitem(last=False)
        return resolved

    def clear_resolution_cache(self) -> None:
        self._resolved.clear()

    @property
    def resolution_cache_size(self) -> int:
        return len(self._resolved)


RUNTIME_DRAWABLES = RuntimeDrawableCatalog()
DRAWABLE_CATALOG = RUNTIME_DRAWABLES.catalog.definitions


def reload_builtin_drawables() -> DrawableCatalog:
    global DRAWABLE_CATALOG
    catalog = RUNTIME_DRAWABLES.reload()
    DRAWABLE_CATALOG = catalog.definitions
    return catalog


def resolve_builtin_drawable(
    drawable_id: str,
    context: DrawableRenderContext,
    *,
    variant: str = "compact",
) -> ResolvedDrawable:
    return RUNTIME_DRAWABLES.resolve(drawable_id, context, variant=variant)
