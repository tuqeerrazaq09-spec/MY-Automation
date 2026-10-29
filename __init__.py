from . import facebook, instagram, linkedin, pinterest, x
from .common import Post, PostError, Skip

REGISTRY = {m.NAME: m for m in (facebook, instagram, linkedin, x, pinterest)}

__all__ = ["REGISTRY", "Post", "PostError", "Skip"]
