"""BDLC: Boundary-Displacement Label Codec (lossless 2D uint16 label maps)."""
from .api import encode, decode, analyze, VERSION

__all__ = ['encode', 'decode', 'analyze', 'VERSION']
