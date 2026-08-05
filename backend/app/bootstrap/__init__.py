"""Development bootstrap public API with lazy module loading."""

__all__ = [
    "DevelopmentBootstrapError",
    "DevelopmentBootstrapResult",
    "bootstrap_development_data",
]


def __getattr__(name: str):
    if name in __all__:
        from app.bootstrap import development

        return getattr(development, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
