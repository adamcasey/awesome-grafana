from .eia_grid import EiaGrid
from .ghcn_christmas import GhcnChristmas
from .hallmark import Hallmark
from .mdc_turkey import MdcTurkey
from .mshp import Mshp
from .nass import Nass
from .white_christmas import WhiteChristmas

REGISTRY = {cls.name: cls for cls in (Hallmark, GhcnChristmas, WhiteChristmas, MdcTurkey, Mshp, EiaGrid, Nass)}
