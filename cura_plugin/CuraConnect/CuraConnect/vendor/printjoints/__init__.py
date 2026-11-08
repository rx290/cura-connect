from .core import FitReport, JointPair, measure_fit, move
from .materials import MATERIALS, PETG, PLA, TPU, Material, get_material
from .dovetail import dovetail
from .snaps import barbed_snap_tenon, barbed_tenon_profile, cantilever_snap_hook, snap_ring

__version__ = "0.1.0"
from .bayonet import bayonet
from .pins import alignment_pins
from .inserts import HEAT_SET, SELF_TAP, heat_set_insert, magnet_pocket, pilot_hole
from .threads import COARSE_PITCH, t_thread, thread
