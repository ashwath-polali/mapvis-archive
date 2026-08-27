"""
compose.py - a brief in, a map SPEC out. The front half that has never existed.

Why this file exists. STATE.md section 1: every artifact this project has produced is
structurally valid and dead, and the reason is that the map was always generated from a
description of SPACE rather than from an intended EXPERIENCE. derive.py measures a real
hillside; vectorise.py traces it; assemble_map.py fires 379 rules on it; every element
has a cause and the result reads as a topographic model. Nothing upstream of the geometry
ever decided what a player would DO, in what order, or what they would be shown when.

So this file generates the JOURNEY first and lets geometry be the residue:

  A  PROGRAM   one organising idea, chosen from a CLOSED NAMED CATALOGUE of the ideas
               observed in docs/THE-PICTURE.md section 2. Selecting a label out of an
               enumerated set is allowed; inventing a layout is not, and no model is
               asked to look at anything or to imagine a placement anywhere in here.
  B  ROUTE     beats before geometry - arrive, narrow, reveal, climb, cross, threshold,
               detour, reward, terminus - with every constraint ORDER-SENSITIVE, so
               frameaudit.py can see it and a permutation of the stations breaks it.
  C  SOLID     L5 dispatch on TYPE, because there is no universal authoring order. Void
               types start from a SOLID and carve; mass types author resistant bodies and
               let the coast follow; sightline types solve the rake and take the bowl as
               residue.
  D  HERO      the organising idea's 8-15 named sub-parts out of kit/, sited on the
               route's principal threshold and stamped as an occluder so it hides the
               terminus until the player is through it.
  E  EMIT      grids + spec.json -> vectorise.build -> geom.json, which build_place.py and
               assemble_map.py already consume unchanged, plus route.json and the
               ops_cause registry.

Two things it deliberately does NOT do. It never renders and never judges - nobody in
this pipeline is allowed to judge that. And when a gate fails it does not nudge anything
by taste: repair is a bounded ENUMERATED search over two knobs (turn scale, room scale)
in a fixed order, first pass wins, and every candidate's numbers are printed so the
choice is auditable.

One honest limitation, stated rather than hidden: the cause registry names the object
names R2 needs, but build_place.py currently names its objects after materials, so R2
cannot pass downstream until the builder honours `hero[].obj` and `causes[].obj`.

    python compose.py --brief "harbour town"
    "C:/Program Files/Blender Foundation/Blender 4.5/blender.exe" -b -P compose.py -- \
        --brief "mountain cave" --carve
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, 'kit'))

import ops_cause as OC                                            # noqa: E402
import ops_solid as OS                                            # noqa: E402
import vectorise as VEC                                           # noqa: E402
import _geom as _g                                                # noqa: E402

CHAR = 1.7
LEVEL = CHAR                     # one walkable level is exactly 1.0 CHAR
RES = 1.0                        # metres per grid cell, as derive.py
MARGIN_M = 14.0                  # solid rim around the plate, so L4 has something to close
STOREY = 3.2                     # build_place.STOREY - a terrace cornice at 6-9 CHAR
CAP_M = 300.0                    # a ray that hits nothing, matching frameaudit.visible_volume
REVEAL_RATIO = 1.45              # frameaudit.report's own event threshold
BUILT_LEVELS = 2                 # a mass occludes at least two levels above its own ground
TIER1_FACTOR = 1.6               # L1: the tier-1 silhouette must exceed 1.6x every other
STOREY_BAND = (4, 14)            # structural sanity limit on the landmark, not a measurement


class ComposeError(ValueError):
    """Raised when the brief, the catalogue or a gate makes the map unbuildable."""


# ===========================================================================
# STAGE A - THE PROGRAM
# ===========================================================================
# L5's table, verbatim. The dispatch is on the declared type and nothing else.
GENERATING_SIDE = {
    'cave': 'void', 'dungeon': 'void', 'town': 'void', 'interior': 'void',
    'island': 'mass', 'coast': 'mass',
    'stadium': 'sightline', 'arena': 'sightline',
}

# Which type a brief's own words declare. Priority matters: when a brief names BOTH a
# water context and a settlement ("harbour town"), the water wins the dispatch, because
# the coastline is the boundary condition every street has to respect. Author the side
# that would otherwise be shapeless - that is exactly the failure L5 says the universal
# void-first rule guarantees.
TYPE_WORDS = {
    'coast': ('harbour', 'harbor', 'port', 'coast', 'quay', 'dock', 'wharf', 'seafront',
              'shore', 'cliff', 'gorge', 'pass'),
    'island': ('island', 'isle', 'atoll', 'archipelago'),
    'cave': ('cave', 'cavern', 'grotto', 'mine', 'shaft', 'chasm', 'sinkhole', 'burrow'),
    'dungeon': ('dungeon', 'tomb', 'crypt', 'catacomb', 'vault'),
    'arena': ('arena', 'amphitheatre', 'amphitheater', 'stadium', 'bowl'),
    'interior': ('interior', 'hall', 'nave', 'cellar', 'chamber', 'tavern'),
    'town': ('town', 'village', 'city', 'street', 'market', 'roofscape'),
}
TYPE_PRIORITY = ('coast', 'island', 'cave', 'dungeon', 'arena', 'interior', 'town')

# The beat vocabulary. One closed table, and every number in it is a construction
# decision that the gates then read back off the geometry.
#   width  corridor width, CHAR          length  advance, CHAR
#   turn   heading change, degrees       dlevel  levels gained
#   kind   space | throat | span | branch room    room radius, CHAR (0 = no room)
BEAT = {
    'arrive':    dict(width=3.2, length=5.0, turn=0,   dlevel=0, kind='space',  room=3.0),
    'narrow':    dict(width=0.95, length=3.5, turn=26, dlevel=0, kind='throat', room=0.0),
    'reveal':    dict(width=4.0, length=6.5, turn=-34, dlevel=0, kind='space',  room=5.5),
    'climb':     dict(width=1.5, length=4.0, turn=18,  dlevel=1, kind='throat', room=0.0),
    'cross':     dict(width=1.1, length=6.5, turn=0,   dlevel=0, kind='span',   room=0.0),
    'threshold': dict(width=1.3, length=2.5, turn=0,   dlevel=0, kind='throat', room=0.0),
    'detour':    dict(width=1.6, length=4.0, turn=72,  dlevel=0, kind='branch', room=0.0),
    'reward':    dict(width=2.0, length=3.0, turn=0,   dlevel=0, kind='space',  room=1.8),
    'terminus':  dict(width=5.0, length=9.0, turn=32,  dlevel=0, kind='space',  room=7.5),
}
SINGLE_FILE_CHAR = 1.0           # a one-lane pier; the route must hit this at least once
STRAIGHT_DEG = 5.0               # below this a station is undeviated and can be an L2 sibling
DEVIATION_DEG = 20.0             # above this a turn needs a co-visible cause

# Where a hero sub-part goes, as fractions of the hero's own span. Closed table, so a
# part cannot be placed anywhere a slot does not already name.
#   (along, across, dlevel)   along = down the route, across = right of it
SLOT = {
    'axis':       (0.00, 0.00, 0),
    'axis_over':  (0.00, 0.00, 1),
    'span':       (0.00, 0.00, 0),
    'span_left':  (0.00, -0.50, 0),
    'span_right': (0.00, 0.50, 0),
    'flank':      (-0.30, 0.50, 0),
    'crown':      (0.00, 0.00, 2),     # the skyline breaker, above whatever crosses overhead
    'toe':        (0.30, 0.00, -1),
    'water':      (0.00, 0.85, -1),
    'interval':   None,          # expands to 3 instances - this is what feeds L2's siblings
}
INTERVAL_ALONG = (-0.35, 0.0, 0.35)

# Beat templates. CONSTRUCTION-THEORY section 5 item 1: the intent sequence cannot be
# generated, and the cheapest legal purchase is a template library per type. This is that
# library, and it is taste compressed once into data rather than taste applied per map.
# Every template ends `reveal, narrow, threshold, terminus`. That tail is not decoration:
# a climax entered from an open space is already spent, because the space before it sees
# it. THE-PICTURE section 2 item 1 and L1's own mechanism both say the same thing - a
# chamber is vast only because the throat was tight - so the last thing before the
# terminus is always a squeeze, and the gate that measures it is G5.
T_WATERFRONT = ('arrive', 'narrow', 'reveal', 'threshold', 'detour', 'reward',
                'cross', 'climb', 'reveal', 'narrow', 'threshold', 'terminus')
T_CLIMB = ('arrive', 'climb', 'narrow', 'reveal', 'detour', 'reward',
           'climb', 'threshold', 'climb', 'reveal', 'narrow', 'threshold', 'terminus')
T_CANYON = ('arrive', 'narrow', 'reveal', 'cross', 'detour', 'reward',
            'narrow', 'climb', 'reveal', 'narrow', 'threshold', 'terminus')
T_UNDER = ('arrive', 'narrow', 'threshold', 'reveal', 'detour', 'reward',
           'narrow', 'cross', 'climb', 'reveal', 'narrow', 'threshold', 'terminus')
T_AXIS = ('arrive', 'narrow', 'reveal', 'climb', 'detour', 'reward',
          'threshold', 'climb', 'reveal', 'narrow', 'threshold', 'terminus')

# The catalogue. Closed, named, and taken from the observed list in THE-PICTURE section 2.
# Each record carries its generating side, its hero part list out of kit/, its occlusion
# rule and its beat template. Nothing else may be composed.
IDEAS = (
    dict(id='canal-with-arches', type='town', side='void', water='channel', aspect='right',
         keywords=('canal', 'arch', 'bridge', 'water street', 'lock'),
         beats=T_WATERFRONT,
         occlusion=dict(hides='terminus', by='circulation.stone_arch_bridge', depth_char=2.4,
                        note='the arch ring and its spandrel eat the far quay'),
         hero=(('circulation.stone_arch_bridge', 'axis'),
               ('thresholds.segmental_arch_culvert', 'axis'),
               ('circulation.quay_water_stair', 'span_left'),
               ('water_terrain.canal_edge_dwarf_wall', 'span'),
               ('water_terrain.quay_wall_coped', 'span_right'),
               ('circulation.balustrade_run', 'crown'),
               ('circulation.newel_pier', 'interval'),
               ('water_terrain.mooring_post', 'water'),
               ('retaining.terrace_edge_kerb', 'toe'),
               ('water_terrain.culvert_arch_outfall', 'flank'),
               ('circulation.boardwalk', 'axis_over'))),
    dict(id='dock-notch', type='coast', side='mass', water='sea', aspect='right',
         keywords=('dock', 'harbour', 'harbor', 'basin', 'notch', 'port', 'slip'),
         beats=T_WATERFRONT,
         occlusion=dict(hides='terminus', by='water_terrain.harbour_arm', depth_char=2.6,
                        note='the arm crosses the mouth so the basin is unseen until inside'),
         hero=(('water_terrain.harbour_arm', 'span'),
               ('water_terrain.quay_wall_coped', 'span_left'),
               ('water_terrain.quay_steps_water', 'axis'),
               ('water_terrain.slipway_ramp', 'toe'),
               ('water_terrain.mooring_post', 'interval'),
               ('water_terrain.quay_guard_post_and_chain', 'flank'),
               ('water_terrain.pile_bent', 'water'),
               ('water_terrain.jetty_deck_timber', 'span_right'),
               ('retaining.timber_crib_bulkhead', 'axis_over'),
               ('circulation.ladder', 'crown'))),
    dict(id='quay-arm', type='coast', side='mass', water='sea', aspect='right',
         keywords=('quay', 'wharf', 'mole', 'breakwater', 'anchorage', 'arm'),
         beats=T_WATERFRONT,
         occlusion=dict(hides='terminus', by='water_terrain.harbour_arm', depth_char=2.2,
                        note='the arm is walked along, so its own length hides its head'),
         hero=(('water_terrain.harbour_arm', 'span'),
               ('water_terrain.quay_wall_coped', 'span_left'),
               ('water_terrain.revetment_battered_rubble', 'toe'),
               ('water_terrain.riprap_apron', 'water'),
               ('water_terrain.mooring_post', 'interval'),
               ('water_terrain.quay_guard_post_and_chain', 'flank'),
               ('water_terrain.quay_steps_water', 'axis'),
               ('circulation.jetty', 'span_right'),
               ('water_terrain.sea_stack_cluster', 'axis_over'),
               ('masses.mass_tower_square_staged', 'crown'))),
    dict(id='pier-into-mist', type='coast', side='mass', water='sea', aspect='right',
         keywords=('pier', 'mist', 'fog', 'jetty', 'landing', 'stage'),
         beats=T_WATERFRONT,
         occlusion=dict(hides='terminus', by='masses.mass_barn_warehouse', depth_char=2.8,
                        note='the net shed on the pier root hides the pier head'),
         hero=(('circulation.jetty', 'axis'),
               ('water_terrain.jetty_deck_timber', 'span'),
               ('water_terrain.pile_bent', 'interval'),
               ('circulation.ladder', 'flank'),
               ('water_terrain.mooring_post', 'span_right'),
               ('circulation.post_rail_guard', 'span_left'),
               ('water_terrain.slipway_ramp', 'toe'),
               ('circulation.boardwalk', 'axis_over'),
               ('water_terrain.beach_foreshore_shelf', 'water'),
               ('masses.mass_barn_warehouse', 'crown'))),
    dict(id='deck-on-trestles', type='town', side='void', water='none', aspect='right',
         keywords=('trestle', 'deck', 'cantilever', 'timber town', 'scaffold'),
         beats=T_UNDER,
         occlusion=dict(hides='terminus', by='circulation.arcaded_viaduct', depth_char=2.4,
                        note='the deck you are on hides what hangs below it'),
         hero=(('circulation.arcaded_viaduct', 'span'),
               ('water_terrain.pile_bent', 'interval'),
               ('circulation.plank_catwalk', 'axis'),
               ('circulation.boardwalk', 'span_left'),
               ('circulation.post_rail_guard', 'span_right'),
               ('circulation.ladder', 'flank'),
               ('masses.mass_jetty_upper', 'crown'),
               ('masses.mass_leanto_outshut', 'water'),
               ('retaining.timber_post_and_rail_guard', 'toe'),
               ('circulation.timber_footbridge', 'axis_over'))),
    dict(id='cliff-switchback', type='coast', side='mass', water='none', aspect='right',
         keywords=('switchback', 'cliff', 'mountain', 'pass', 'hairpin', 'ledge'),
         beats=T_CLIMB,
         occlusion=dict(hides='terminus', by='water_terrain.crown_block_tor', depth_char=3.0,
                        note='the rock nose jutting into the road eats the next leg'),
         hero=(('retaining.cliff_revetment_strata', 'span'),
               ('circulation.quarter_turn_stair', 'axis'),
               ('retaining.raking_cheek_wall', 'span_left'),
               ('retaining.buttressed_retaining_wall', 'span_right'),
               ('circulation.newel_pier', 'interval'),
               ('water_terrain.strata_bench', 'toe'),
               ('water_terrain.talus_scree_toe', 'water'),
               ('circulation.balustrade_run', 'flank'),
               ('water_terrain.crown_block_tor', 'crown'),
               ('circulation.ramp_kerbed', 'axis_over'))),
    dict(id='ceremonial-stair-axis', type='town', side='void', water='none', aspect='right',
         keywords=('ceremonial', 'processional', 'axis', 'statue', 'temple stair'),
         beats=T_AXIS,
         occlusion=dict(hides='terminus', by='masses.mass_civic_bar', depth_char=2.6,
                        note='the flanking civic bar hides the head of the flight'),
         hero=(('circulation.monumental_stair', 'axis'),
               ('circulation.flight_with_landing', 'axis_over'),
               ('retaining.stepped_plinth_crepidoma', 'toe'),
               ('retaining.stone_balustrade', 'span_left'),
               ('retaining.pierced_arcade_parapet', 'span_right'),
               ('circulation.newel_pier', 'interval'),
               ('retaining.raking_cheek_wall', 'flank'),
               ('masses.roof_pediment_portico', 'crown'),
               ('thresholds.round_arch_arcade_bay', 'water'),
               ('masses.mass_civic_bar', 'span'))),
    dict(id='street-canyon', type='town', side='void', water='none', aspect='right',
         keywords=('street', 'canyon', 'lane', 'alley', 'backstreet', 'facade'),
         beats=T_CANYON,
         occlusion=dict(hides='terminus', by='masses.mass_row_terrace', depth_char=2.8,
                        note='the street wall bends, so the tower base never shows early'),
         hero=(('masses.mass_row_terrace', 'span_left'),
               ('masses.mass_arcade_ground', 'span_right'),
               ('thresholds.arched_doorway', 'interval'),
               ('masses.eaves_sprocket_bellcast', 'crown'),
               ('masses.chimney_stack', 'axis_over'),
               ('masses.dormer_gabled', 'water'),
               ('retaining.building_plinth_base_course', 'toe'),
               ('thresholds.covered_passage', 'span'),
               ('circulation.balustrade_run', 'flank'),
               ('masses.mass_tower_square_staged', 'axis'))),
    dict(id='ring-around-a-core', type='cave', side='void', water='none', aspect='right',
         keywords=('ring', 'core', 'grotto', 'loop', 'around'),
         beats=T_UNDER,
         occlusion=dict(hides='terminus', by='water_terrain.crown_block_tor', depth_char=3.4,
                        note='the solid core is permanently between you and the far side'),
         hero=(('water_terrain.crown_block_tor', 'axis'),
               ('thresholds.cave_mouth', 'span'),
               ('circulation.plank_catwalk', 'span_left'),
               ('circulation.ladder', 'flank'),
               ('water_terrain.rock_spire', 'crown'),
               ('water_terrain.boulder', 'interval'),
               ('water_terrain.talus_scree_toe', 'toe'),
               ('circulation.log_riser_step_run', 'water'),
               ('thresholds.rock_overhang', 'axis_over'),
               ('water_terrain.strata_bench', 'span_right'))),
    dict(id='stepped-gorge', type='coast', side='mass', water='sea', aspect='right',
         keywords=('gorge', 'stepped', 'dry-stone', 'river', 'terraced'),
         beats=T_CLIMB,
         occlusion=dict(hides='terminus', by='retaining.stepped_setback_revetment', depth_char=2.2,
                        note='each retaining tier hides the tier above it'),
         hero=(('retaining.stepped_setback_revetment', 'span'),
               ('retaining.coursed_retaining_wall', 'span_left'),
               ('retaining.wing_wall', 'span_right'),
               ('circulation.straight_flight', 'axis'),
               ('circulation.cheek_wall', 'flank'),
               ('retaining.terrace_edge_kerb', 'toe'),
               ('water_terrain.weir_sill', 'water'),
               ('water_terrain.riverbank_undercut_lip', 'axis_over'),
               ('circulation.newel_pier', 'interval'),
               ('water_terrain.waterfall_lip_notch', 'crown'))),
    dict(id='causeway-over-void', type='cave', side='void', water='none', aspect='right',
         keywords=('causeway', 'land-bridge', 'void', 'span', 'abyss'),
         beats=T_UNDER,
         occlusion=dict(hides='terminus', by='circulation.arcaded_viaduct', depth_char=2.4,
                        note='the causeway parapet crops the far shore until mid-span'),
         hero=(('circulation.arcaded_viaduct', 'span'),
               ('circulation.stone_arch_bridge', 'axis'),
               ('retaining.pierced_arcade_parapet', 'span_left'),
               ('circulation.balustrade_run', 'span_right'),
               ('circulation.newel_pier', 'interval'),
               ('water_terrain.rock_spire', 'water'),
               ('water_terrain.boulder', 'toe'),
               ('thresholds.arcaded_parapet', 'crown'),
               ('circulation.plank_catwalk', 'axis_over'),
               ('water_terrain.talus_scree_toe', 'flank'))),
    dict(id='roofscape', type='town', side='void', water='none', aspect='right',
         keywords=('roof', 'roofscape', 'rooftop', 'skyline', 'tiles'),
         beats=T_CANYON,
         occlusion=dict(hides='terminus', by='masses.roof_gable_prism', depth_char=2.6,
                        note='the near ridge line hides the keep base, which is what makes it far'),
         hero=(('masses.roof_gable_prism', 'span'),
               ('masses.roof_hip', 'span_left'),
               ('masses.roof_mansard', 'span_right'),
               ('masses.dormer_gabled', 'interval'),
               ('masses.chimney_stack', 'crown'),
               ('masses.parapet_balustrade_finials', 'axis_over'),
               ('masses.eaves_sprocket_bellcast', 'toe'),
               ('circulation.ladder', 'flank'),
               ('masses.cross_gable_wall_dormer', 'axis'),
               ('circulation.plank_catwalk', 'water'))),
    dict(id='monument-over-village', type='town', side='void', water='none', aspect='right',
         keywords=('monument', 'academy', 'cathedral', 'over', 'village', 'landmark'),
         beats=T_AXIS,
         occlusion=dict(hides='terminus', by='masses.mass_box_house', depth_char=2.8,
                        note='ordinary houses hide the monument base, which is the whole scale trick'),
         hero=(('masses.mass_tower_square_staged', 'axis'),
               ('masses.roof_dome_lantern', 'crown'),
               ('retaining.stepped_plinth_crepidoma', 'toe'),
               ('circulation.monumental_stair', 'axis_over'),
               ('masses.mass_box_house', 'span_left'),
               ('masses.mass_leanto_outshut', 'span_right'),
               ('thresholds.arched_doorway', 'water'),
               ('retaining.low_boundary_wall_with_pier_stops', 'span'),
               ('circulation.newel_pier', 'interval'),
               ('masses.gable_porch_entry', 'flank'))),
    dict(id='worksite', type='cave', side='void', water='none', aspect='right',
         keywords=('mine', 'worksite', 'headframe', 'excavation', 'industrial', 'quarry'),
         beats=T_UNDER,
         occlusion=dict(hides='terminus', by='masses.mass_barn_warehouse', depth_char=2.6,
                        note='the ore shed and its hopper block the pit head'),
         hero=(('masses.mass_barn_warehouse', 'span'),
               ('circulation.plank_catwalk', 'axis_over'),
               ('water_terrain.boulder', 'interval'),
               ('thresholds.timber_tunnel_portal', 'axis'),
               ('circulation.ladder', 'flank'),
               ('circulation.boardwalk', 'span_left'),
               ('retaining.timber_crib_bulkhead', 'span_right'),
               ('water_terrain.talus_scree_toe', 'toe'),
               ('water_terrain.rock_spire', 'crown'),
               ('circulation.log_riser_step_run', 'water'))),
    dict(id='flooded-chasm', type='cave', side='void', water='channel', aspect='right',
         keywords=('flooded', 'chasm', 'cistern', 'crypt', 'drowned', 'waterway'),
         beats=T_UNDER,
         occlusion=dict(hides='terminus', by='thresholds.cave_mouth', depth_char=2.8,
                        note='the chamber lip crops the cataract until you are on the plank'),
         hero=(('water_terrain.culvert_arch_outfall', 'span'),
               ('circulation.plank_catwalk', 'axis_over'),
               ('water_terrain.pile_bent', 'water'),
               ('circulation.timber_footbridge', 'axis'),
               ('water_terrain.riverbank_undercut_lip', 'toe'),
               ('water_terrain.boulder', 'interval'),
               ('thresholds.cave_mouth', 'span_left'),
               ('water_terrain.waterfall_lip_notch', 'crown'),
               ('circulation.ladder', 'flank'),
               ('water_terrain.strata_bench', 'span_right'))),
    dict(id='switchback-in-whiteout', type='coast', side='mass', water='none', aspect='right',
         keywords=('whiteout', 'snow', 'blizzard', 'storm', 'defile', 'brazier'),
         beats=T_CLIMB,
         occlusion=dict(hides='terminus', by='retaining.coursed_retaining_wall', depth_char=2.4,
                        note='the retained bend plus the whiteout deletes everything past one leg'),
         hero=(('circulation.quarter_turn_stair', 'axis'),
               ('retaining.coursed_retaining_wall', 'span'),
               ('retaining.buttressed_retaining_wall', 'span_left'),
               ('circulation.post_rail_guard', 'span_right'),
               ('circulation.newel_pier', 'interval'),
               ('water_terrain.talus_scree_toe', 'toe'),
               ('water_terrain.crown_block_tor', 'crown'),
               ('circulation.ramp_kerbed', 'axis_over'),
               ('retaining.wing_wall', 'flank'),
               ('water_terrain.boulder', 'water'))),
    dict(id='sinkhole-with-one-shaft', type='cave', side='void', water='none', aspect='right',
         keywords=('sinkhole', 'shaft', 'daylight', 'column of light', 'quicksand'),
         beats=T_CLIMB,
         occlusion=dict(hides='terminus', by='water_terrain.shelf_cliff_plate', depth_char=3.2,
                        note='the overhanging shelf hides the lit floor until you are under it'),
         hero=(('thresholds.rock_overhang', 'crown'),
               ('water_terrain.shelf_cliff_plate', 'span'),
               ('circulation.corner_wrap_stair', 'axis'),
               ('water_terrain.talus_scree_toe', 'toe'),
               ('water_terrain.boulder', 'interval'),
               ('circulation.ladder', 'flank'),
               ('water_terrain.rock_spire', 'span_left'),
               ('water_terrain.strata_bench', 'span_right'),
               ('water_terrain.cave_mouth_portal', 'axis_over'),
               ('circulation.log_riser_step_run', 'water'))),
)

# What a dead end pays. Closed table by type, so "every dead end pays something" is
# structural rather than remembered.
PAYLOAD = {
    'cave': ('ore_node', 'chest', 'rare_encounter'),
    'dungeon': ('chest', 'relic_stele', 'rare_encounter'),
    'town': ('npc_vignette', 'chest', 'shrine'),
    'interior': ('npc_vignette', 'chest', 'shrine'),
    'coast': ('moored_boat', 'chest', 'npc_vignette'),
    'island': ('moored_boat', 'chest', 'shrine'),
    'arena': ('chest', 'npc_vignette', 'shrine'),
    'stadium': ('chest', 'npc_vignette', 'shrine'),
}
# The cause vocabulary a type is allowed to blame a bend on, out of ops_cause.CAUSE_KINDS.
CAUSE_KIND = {'cave': 'fault_plane', 'dungeon': 'bedding_parting', 'town': 'older_structure',
              'interior': 'older_structure', 'coast': 'outcrop', 'island': 'outcrop',
              'arena': 'grade_break', 'stadium': 'grade_break'}


def _gate_catalogue():
    """Every catalogue entry checked at import, so a typo fails here and not in a render.

    The kit part names are resolved against the real modules: an idea that names a part
    the kit does not have is a fiction, and the whole point of a closed catalogue is that
    it cannot contain one."""
    import importlib
    mods = {}
    for m in ('retaining', 'circulation', 'masses', 'thresholds', 'water_terrain'):
        mods[m] = importlib.import_module(m)
    seen = set()
    for beat, rec in BEAT.items():
        if rec['dlevel'] and rec['kind'] != 'throat':
            raise ComposeError(f"beat {beat!r} spends elevation on a {rec['kind']}; L1 says "
                               f"elevation is spent at THROATS, never across open plates")
    for idea in IDEAS:
        i = idea['id']
        if i in seen:
            raise ComposeError(f"duplicate catalogue id {i!r}")
        seen.add(i)
        if GENERATING_SIDE.get(idea['type']) != idea['side']:
            raise ComposeError(f"{i}: type {idea['type']!r} is {GENERATING_SIDE.get(idea['type'])!r} "
                               f"under L5, record says {idea['side']!r}")
        if not 8 <= len(idea['hero']) <= 15:
            raise ComposeError(f"{i}: hero has {len(idea['hero'])} parts, wanted 8-15")
        for part, slot in idea['hero']:
            mod, fn = part.split('.')
            if mod not in mods or not hasattr(mods[mod], fn):
                raise ComposeError(f"{i}: kit has no {part}")
            if slot not in SLOT:
                raise ComposeError(f"{i}: slot {slot!r} is not in the slot table")
        if idea['occlusion']['by'] not in dict(idea['hero']):
            raise ComposeError(f"{i}: occluder {idea['occlusion']['by']!r} is not one of its "
                               f"own hero parts")
        b = idea['beats']
        if b[-1] != 'terminus' or b.count('terminus') != 1:
            raise ComposeError(f"{i}: beats must end in exactly one terminus")
        nrev = b.count('reveal')
        if not 2 <= nrev <= 5:
            raise ComposeError(f"{i}: {nrev} reveal beats, L1 allows 2-5")
        if not any(BEAT[x]['width'] <= SINGLE_FILE_CHAR for x in b):
            raise ComposeError(f"{i}: route never narrows to single file")
        straight = sum(1 for x in b if abs(BEAT[x]['turn']) < STRAIGHT_DEG)
        if straight < OC.SIBLINGS_REQUIRED:
            raise ComposeError(f"{i}: only {straight} straight stations, L2 needs "
                               f"{OC.SIBLINGS_REQUIRED} undeviated siblings")
        # a branch must be closed by a reward, or the dead end pays nothing
        depth = 0
        for x in b:
            if BEAT[x]['kind'] == 'branch':
                if depth:
                    raise ComposeError(f"{i}: nested detour")
                depth = 1
            elif depth and x == 'reward':
                depth = 0
        if depth:
            raise ComposeError(f"{i}: a detour is never paid by a reward")
    return len(IDEAS)


N_IDEAS = _gate_catalogue()


def select(brief, type_override=None):
    """Stage A. A label out of a closed set: declared type first, then keyword count,
    then catalogue order. No model reads the brief and nothing is invented."""
    words = brief.lower().replace('-', ' ').replace(',', ' ')
    hits = []
    for t in TYPE_PRIORITY:
        for w in TYPE_WORDS[t]:
            if w in words:
                hits.append(t)
                break
    typ = type_override or (hits[0] if hits else None)
    if typ and typ not in GENERATING_SIDE:
        raise ComposeError(f"type {typ!r} is not in the L5 table {tuple(GENERATING_SIDE)}")
    # a DECLARED type overrides the L5 row without narrowing the catalogue: the type says
    # which side to author, the idea says what the place is about, and they are separate
    # choices. Only a type read out of the brief's own words filters the pool.
    pool = list(IDEAS) if type_override else (
        [i for i in IDEAS if i['type'] == typ] if typ else list(IDEAS))
    if not pool:
        raise ComposeError(f"no catalogue idea has type {typ!r}; the catalogue is closed and "
                           f"nothing may be invented for it")
    scored = []
    for idea in pool:
        k = [w for w in idea['keywords'] if w in words]
        scored.append((len(k), -IDEAS.index(idea), idea, k))
    scored.sort(reverse=True)
    best = scored[0]
    if best[0] == 0 and not typ:
        raise ComposeError(f"brief {brief!r} matched no type word and no catalogue keyword. "
                           f"Guessing is banned; name one of {[i['id'] for i in IDEAS]}")
    resolved = typ or best[2]['type']
    # THE SIDE AND THE TYPE ARE SEPARATE QUESTIONS. The type says what the place IS and
    # picks the idea; the side says which half of the solid to author. A SETTLEMENT word
    # beats a WATER word on the side only, because the side is a question about the FABRIC.
    # "harbour town" resolved to coast, which is mass-authored, which stamps a handful of
    # rects at stations: 5 blocks and 3.5% built over 106 m, an empty plate the audit could
    # only report as four meaningless failures. A harbour town is a DENSE TOWN that happens
    # to meet water - author the void, and let the water supply L4's open arc.
    side = GENERATING_SIDE[resolved]
    if not type_override and 'town' in hits and side == 'mass':
        side = 'void'
    return dict(idea=best[2], type=resolved, side=side, keyword_hits=best[3],
                type_hits=hits, by_type_only=(best[0] == 0))


# ===========================================================================
# STAGE B - THE ROUTE AND THE BEATS
# ===========================================================================
def walk_beats(idea, turn_scale=1.0, room_scale=1.0):
    """The journey, before any geometry exists. A turtle over the beat template.

    Turn signs alternate per turning beat over the body of the route, which is what stops
    a template from unrolling into one long arc, and it is a rule rather than a taste call.

    From the LAST REVEAL onward the signs stop alternating and every turn bends the same
    way. Measured reason: with alternating signs the reveal's -34 and the following
    narrow's +26 cancel, the tail unrolls into a straight 45 m run, and the terminus is
    visible from three stations before its own threshold (G5 leaks [6,7,8], measured).
    A climax has to be entered around a corner, so the tail is one consistent bend.

    A branch beat pushes the turtle state and the following beats form a spur until a
    reward pops it, so a dead end is a real spur that ends in a payload and never a stub
    on the main line."""
    x, y, a, lv = 0.0, 0.0, math.pi / 2, 0
    turns = 0
    stations, spurs = [], []
    spur, saved = None, None
    payloads = PAYLOAD[idea['type']]
    tail = max(i for i, b in enumerate(idea['beats']) if b == 'reveal')

    for n, beat in enumerate(idea['beats']):
        rec = BEAT[beat]
        if rec['kind'] == 'branch':
            saved = (x, y, a, lv)
            spur = []
        sign = 1 if n >= tail else (1 if turns % 2 == 0 else -1)
        base = abs(rec['turn']) if n >= tail else rec['turn']
        dturn = base * turn_scale * sign
        if rec['turn']:
            a += math.radians(dturn)
            turns += 1
        lv += rec['dlevel']
        st = dict(i=len(stations) if spur is None else -1, beat=beat, x=x, y=y, level=lv,
                  width=rec['width'] * CHAR, room=rec['room'] * CHAR * room_scale,
                  turn=dturn if rec['turn'] else 0.0, kind=rec['kind'],
                  heading=a, length=rec['length'] * CHAR)
        ln = rec['length'] * CHAR
        x, y = x + math.cos(a) * ln, y + math.sin(a) * ln
        st['ex'], st['ey'] = x, y
        (spur if spur is not None else stations).append(st)
        if spur is not None and beat == 'reward':
            spurs.append(dict(stations=spur, payload=payloads[len(spurs) % len(payloads)]))
            x, y, a, lv = saved
            spur = None

    # one extra station INSIDE the terminus room, because the beat station stands at the
    # room's mouth and L1's global maximum belongs where the space actually opens
    last = stations[-1]
    mx, my = (last['x'] + last['ex']) * 0.5, (last['y'] + last['ey']) * 0.5
    stations.append(dict(i=len(stations), beat='terminus_in', x=mx, y=my,
                         level=last['level'], width=last['width'], room=last['room'],
                         turn=0.0, kind='space', heading=last['heading'],
                         length=0.0, ex=last['ex'], ey=last['ey']))
    for n, st in enumerate(stations):
        st['i'] = n
    return dict(stations=stations, spurs=spurs, turn_scale=turn_scale,
                room_scale=room_scale)


def route_polyline(route):
    """The main line as frameaudit wants it: x,y,z with z on the walk surface."""
    pts = [[round(s['x'], 2), round(s['y'], 2), round(s['level'] * LEVEL, 2)]
           for s in route['stations']]
    last = route['stations'][-1]
    pts.append([round(last['ex'], 2), round(last['ey'], 2), round(last['level'] * LEVEL, 2)])
    return pts


def principal_threshold(route):
    """Where the hero goes. The last throat before the terminus, preferring a declared
    threshold beat, because that is the gate the player comes through."""
    sts = route['stations']
    for st in reversed(sts[:-2]):
        if st['beat'] == 'threshold':
            return st
    for st in reversed(sts[:-2]):
        if st['kind'] == 'throat':
            return st
    raise ComposeError('no throat before the terminus, so the hero has nowhere to stand')


# ===========================================================================
# STAGE C - THE SOLID (L5 dispatch on type)
# ===========================================================================
def all_stations(route):
    return route['stations'] + [s for sp in route['spurs'] for s in sp['stations']]


def plate(route):
    """The grid the whole map lives on. Square, like derive.py's window, with a solid rim
    of MARGIN_M so L4 has near-field mass to close the horizon with instead of the map
    simply running out."""
    sts = all_stations(route)
    xs, ys, r = [], [], []
    for s in sts:
        xs += [s['x'], s['ex']]
        ys += [s['y'], s['ey']]
        r.append(max(s['room'], s['width'] * 0.5) + MARGIN_M)
    pad = max(r)
    x0, x1 = min(xs) - pad, max(xs) + pad
    y0, y1 = min(ys) - pad, max(ys) + pad
    span = max(x1 - x0, y1 - y0)
    n = int(math.ceil(span / RES))
    return dict(ox=x0, oy=y0, span=round(n * RES, 2), n=n)


def _mesh_xy(pl):
    idx = np.arange(pl['n'], dtype=np.float64)
    return np.meshgrid(idx * RES + pl['ox'], idx * RES + pl['oy'])


def stamp_capsule(mask, ax, ay, bx, by, half_w, X, Y):
    """A segment thickened to a width, ends rounded. This is a street, an alley, a pier
    deck and a headland spine alike, and it is the only plan primitive here."""
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 < 1e-9:
        d2 = (X - ax) ** 2 + (Y - ay) ** 2
    else:
        t = np.clip(((X - ax) * dx + (Y - ay) * dy) / L2, 0.0, 1.0)
        d2 = (X - (ax + t * dx)) ** 2 + (Y - (ay + t * dy)) ** 2
    mask |= d2 <= half_w * half_w


def stamp_rect(mask, cx, cy, ux, uy, along, across, X, Y):
    """An oriented rectangle: the hero occluder footprint and the tier-1 precinct."""
    px, py = -uy, ux
    a = (X - cx) * ux + (Y - cy) * uy
    b = (X - cx) * px + (Y - cy) * py
    mask |= (np.abs(a) <= along * 0.5) & (np.abs(b) <= across * 0.5)


def corridor_masks(route, pl, X, Y):
    """The walkable void: every beat segment at its own width, and every room swept ALONG
    its own beat instead of dropped as a disc at the midpoint.

    The long axis is not cosmetic. What the sight fan measures is a room's depth in the
    view direction, so sweeping it makes the terminus - which owns both the largest room
    radius and the longest beat - the deepest space in the map by construction rather than
    by luck, and that is what L1's global-maximum clause needs. A nave, a plaza and a
    harbour basin all have their long axis along the approach in any case.

    A room is also CLIPPED to the half-plane in front of its own station, which is not a
    detail. A 12.75 m terminus room swept over a 15 m leg otherwise reaches 5 m back past
    its own mouth, swallows the 4 m threshold and the 6 m narrow whole, and the map has no
    throat left anywhere - measured as G5 leaking from three stations at once. You stand at
    the mouth of a space and it opens AHEAD of you."""
    walk = np.zeros((pl['n'], pl['n']), bool)
    rooms = np.zeros_like(walk)
    tmp = np.zeros_like(walk)
    for s in all_stations(route):
        stamp_capsule(walk, s['x'], s['y'], s['ex'], s['ey'], s['width'] * 0.5, X, Y)
        if s['room'] > 0:
            tmp[:] = False
            stamp_capsule(tmp, s['x'], s['y'], s['ex'], s['ey'], s['room'], X, Y)
            ux, uy = math.cos(s['heading']), math.sin(s['heading'])
            rooms |= tmp & (((X - s['x']) * ux + (Y - s['y']) * uy) >= 0.0)
    return walk | rooms, rooms


def level_field(route, pl, X, Y):
    """Nearest-station level. A level only ever changes at a climb beat, and the BEAT
    table's own import gate forbids a climb anywhere but a throat, so every level change
    in the finished map lands in a neck between two spaces. That is L1's elevation clause
    made structural instead of remembered."""
    best = np.full((pl['n'], pl['n']), np.inf)
    lvl = np.zeros((pl['n'], pl['n']), np.int16)
    for s in all_stations(route):
        mx, my = (s['x'] + s['ex']) * 0.5, (s['y'] + s['ey']) * 0.5
        d = (X - mx) ** 2 + (Y - my) ** 2
        take = d < best
        best = np.where(take, d, best)
        lvl = np.where(take, np.int16(s['level']), lvl)
    return lvl


def channel_mask(route, pl, X, Y):
    """A water channel beside the route, on the idea's aspect side. This is what a
    canal-with-arches and a flooded-chasm are, and it is what makes a cross beat a real
    bridge instead of a change of paving."""
    m = np.zeros((pl['n'], pl['n']), bool)
    for s in route['stations']:
        ux, uy = math.cos(s['heading']), math.sin(s['heading'])
        px, py = -uy, ux
        off = s['width'] * 0.5 + 1.4 * CHAR
        stamp_capsule(m, s['x'] + px * off, s['y'] + py * off,
                      s['ex'] + px * off, s['ey'] + py * off, 1.25 * CHAR, X, Y)
    return m


def solid(route, idea, pl, typ=None, side=None):
    """L5's table as a dispatch and nothing cleverer."""
    side = side or GENERATING_SIDE[typ or idea['type']]
    X, Y = _mesh_xy(pl)
    walk, rooms = corridor_masks(route, pl, X, Y)
    lvl = level_field(route, pl, X, Y)
    fn = {'void': _solid_void, 'mass': _solid_mass, 'sightline': _solid_sightline}[side]
    g = fn(route, idea, pl, X, Y, walk, lvl)
    g['side'] = side
    g['rooms'] = rooms
    g['X'], g['Y'] = X, Y
    return g


def _solid_void(route, idea, pl, X, Y, walk, lvl):
    """Cave, dungeon, dense town, interior: author the VOID, mass is the complement.

    built = land & ~walk, so the streets are SLOTS cut through one continuous solid and a
    door is a hole in a wall you are already touching. THE-PICTURE section 6 item 15: a
    field of detached boxes with uniform gaps is a car park with sheds on it."""
    land = np.ones((pl['n'], pl['n']), bool)
    water = np.zeros_like(land)
    if idea['water'] == 'channel':
        water = channel_mask(route, pl, X, Y) & ~walk
        land &= ~water
    alleys = alley_mask(route, pl, X, Y)
    return dict(land=land, walk=walk & land, built=land & ~walk & ~alleys, water=water,
                lvl=lvl, alleys=alleys)


ALLEY_PITCH_M = 18.0             # so no party-wall mass runs longer than this between gaps
ALLEY_HALF_M = 1.1              # STATE.md section 4: the real stepped alleys are 2-3 m


def alley_mask(route, pl, X, Y):
    """Service slots cut off the route at a fixed pitch, perpendicular, out to the rim.

    Without them the void branch is ONE mass with one slot in it, and the block trace comes
    back as an 88 m slab - the ribbon defect STATE.md section 4 records as the corrugation
    bug (47 strips, longest 120 m). The pitch is what caps a block's length, so it is also
    what makes L1's tier-1 clause satisfiable at all: a landmark cannot out-silhouette an
    88 m wall without becoming a 16-storey tower.

    They are void but NOT walkable: they are the 2-3 m gap between party-wall masses, so
    they cut the trace without adding walkable area or opening a sightline."""
    m = np.zeros((pl['n'], pl['n']), bool)
    reach = pl['span']
    for s in route['stations']:
        ux, uy = math.cos(s['heading']), math.sin(s['heading'])
        px, py = -uy, ux
        L = math.hypot(s['ex'] - s['x'], s['ey'] - s['y'])
        t = 0.0
        while t <= L + 1e-6:
            bx, by = s['x'] + ux * t, s['y'] + uy * t
            for side in (-1.0, 1.0):
                stamp_capsule(m, bx + px * side * s['width'] * 0.5,
                              by + py * side * s['width'] * 0.5,
                              bx + px * side * reach, by + py * side * reach,
                              ALLEY_HALF_M, X, Y)
            t += ALLEY_PITCH_M
    return m


def _solid_mass(route, idea, pl, X, Y, walk, lvl):
    """Island and coast: author the MASS, the coast follows.

    A resistant body flanks each beat on both sides and stands ONE LEVEL above the route
    it flanks, which is what makes it a headland and what closes the horizon. The body is
    omitted on the aspect side at a reveal and at the terminus, and that omission is the
    only place the sea reaches the route - so L4's one-to-two open arcs and L1's global
    maximum at the terminus fall out of the same rule instead of being two separate
    fixes. Everything the bodies do not cover is water, so the coastline is traced and
    never drawn."""
    n = pl['n']
    body = np.zeros((n, n), bool)
    aspect = 1.0 if idea['aspect'] == 'right' else -1.0
    for s in all_stations(route):
        ux, uy = math.cos(s['heading']), math.sin(s['heading'])
        px, py = -uy, ux
        bw = max(6.0 * CHAR, s['width'] * 2.5)
        core = max(s['room'], s['width'] * 0.5)
        for side in (-1.0, 1.0):
            ax, ay, bx, by = s['x'], s['y'], s['ex'], s['ey']
            if s['beat'] in ('reveal', 'terminus', 'terminus_in') and side == aspect:
                if s['beat'] != 'reveal':
                    continue
                # a mid-route reveal is a glimpse, the terminus is the arrival: the glimpse
                # keeps its body over the first three quarters of the leg
                ax, ay = ax + (bx - ax) * 0.75, ay + (by - ay) * 0.75
            off = core + bw * 0.5
            stamp_capsule(body, ax + px * off * side, ay + py * off * side,
                          bx + px * off * side, by + py * off * side, bw * 0.5, X, Y)
    land = body | walk
    lvl = np.where(body & ~walk, lvl + 1, lvl).astype(np.int16)
    built = np.zeros((n, n), bool)
    for s in route['stations']:
        if s['kind'] != 'space':
            continue
        ux, uy = math.cos(s['heading']), math.sin(s['heading'])
        px, py = -uy, ux
        core = max(s['room'], s['width'] * 0.5)
        for side in (-1.0, 1.0):
            if s['beat'] in ('reveal', 'terminus', 'terminus_in') and side == aspect:
                continue
            cx = (s['x'] + s['ex']) * 0.5 + px * (core + 4.0) * side
            cy = (s['y'] + s['ey']) * 0.5 + py * (core + 4.0) * side
            stamp_rect(built, cx, cy, ux, uy, max(9.0, s['length']), 7.0, X, Y)
    built &= land & ~walk
    water = ~land
    lvl = np.where(water, np.int16(-1), lvl)
    return dict(land=land, walk=walk & land, built=built, water=water, lvl=lvl)


def _solid_sightline(route, idea, pl, X, Y, walk, lvl):
    """Stadium, theatre, arena: author the SIGHTLINE SURFACE, the bowl void is the residue.

    The real constant-C recurrence rather than a cosmetic slope: for a row at horizontal
    distance D from the focus with eye height N above it, the next row's eye height is
    N' = ((N + C) * (D + d)) / D, with C the clearance over the head in front. The rake is
    then quantised to whole LEVELs, so the bowl is a stepped terrace whose step positions
    were solved and not chosen."""
    n = pl['n']
    C_VAL, ROW_D = 0.09, 0.80
    focus = route['stations'][-1]
    fx, fy = focus['ex'], focus['ey']
    rows, D, N = [], max(6.0, focus['room']), 1.2
    while D < pl['span'] * 0.45:
        rows.append((D, N))
        N = ((N + C_VAL) * (D + ROW_D)) / D
        D += ROW_D
    R = np.sqrt((X - fx) ** 2 + (Y - fy) ** 2)
    lvl = np.zeros((n, n), np.int16)
    for D, N in rows:
        lvl = np.where(R >= D, np.int16(max(0, int(N / LEVEL))), lvl)
    bowl = R <= rows[-1][0]
    walk = walk | bowl
    land = np.ones((n, n), bool)
    return dict(land=land, walk=walk, built=land & ~walk, water=np.zeros((n, n), bool),
                lvl=lvl, rows=len(rows))


# ===========================================================================
# STAGE B GATES - measured off the solid, because a route is only a claim until
# the geometry it implies is standing
# ===========================================================================
BASE_STOREYS = 3                 # a terrace row; build_place defaults to 3 as well
FAN_RAYS = 9                     # frameaudit casts 17x17 in 3D; this is the plan fan
FAN_HALF = math.radians(25.0)    # frameaudit's fov is 50 degrees
COVER_RAYS = 64
MAX_COVER = 0.60                 # above this the map is spent from one station
TURN_LADDER = (1.0, 1.2, 1.45, 1.7, 2.0)
ROOM_LADDER = (1.0, 1.15, 0.85, 1.3, 0.75)


def occ_field(g):
    """What blocks a sightline, in whole levels, so the plan test is really 2.5D.

    Water is impassable and TRANSPARENT - L1's machine form says getting that backwards
    inverts every shoreline, balcony and terrace in the reference set. Bare high ground
    occludes at its own relief; a mass occludes BUILT_LEVELS above its ground."""
    occ = g['lvl'].astype(np.int16).copy()
    occ[g['built']] = (g['lvl'][g['built']] + BUILT_LEVELS).astype(np.int16)
    occ[g['water']] = np.int16(-99)
    return occ


def _ray(occ, base, x, y, dx, dy, pl, cap=CAP_M):
    """Distance to the first thing that blocks the view, marching in half-metre steps.
    A ray that leaves the plate returns `cap`, exactly as frameaudit returns 300 m for a
    ray that hits nothing - so an open arc of sea dominates the series, which is the real
    difficulty L1 names for coasts rather than something to smooth away."""
    n = pl['n']
    ox, oy = pl['ox'], pl['oy']
    d = 0.5
    while d <= cap:
        cx = int((x + dx * d - ox) / RES)
        cy = int((y + dy * d - oy) / RES)
        if not (0 <= cx < n and 0 <= cy < n):
            return cap
        if occ[cy, cx] > base:
            return d
        d += 0.5
    return cap


def sight_series(route, occ, pl):
    """The target visible-volume series: mean of r^2 over a plan fan at every station, in
    route order. Same construction as frameaudit.visible_volume, one dimension down, so
    the numbers are comparable in shape and the gates below are order-sensitive."""
    out = []
    for s in route['stations']:
        h = s['heading']
        tot = 0.0
        for k in range(FAN_RAYS):
            a = h + (k / (FAN_RAYS - 1) - 0.5) * 2 * FAN_HALF
            r = _ray(occ, s['level'], s['x'], s['y'], math.cos(a), math.sin(a), pl)
            tot += r * r
        out.append(tot / FAN_RAYS)
    return out


def sees(occ, base, ax, ay, bx, by, pl):
    """Is B visible from A. Marches to B and reports whether anything got in the way."""
    dx, dy = bx - ax, by - ay
    L = math.hypot(dx, dy)
    if L < 1e-6:
        return True
    return _ray(occ, base, ax, ay, dx / L, dy / L, pl, cap=L) >= L - 0.5


def isovist_cover(occ, walk, base, x, y, pl):
    """Fraction of the walkable map visible from one station. CONSTRUCTION-THEORY's Stage B
    sanity check: a map visible in its entirety from any single walkable point is spent in
    one frame."""
    n = pl['n']
    ox, oy = pl['ox'], pl['oy']
    tot = int(walk.sum())
    if not tot:
        return 1.0
    seen = np.zeros_like(walk)
    for k in range(COVER_RAYS):
        a = 2 * math.pi * k / COVER_RAYS
        dx, dy = math.cos(a), math.sin(a)
        d = 0.5
        while d <= CAP_M:
            cx = int((x + dx * d - ox) / RES)
            cy = int((y + dy * d - oy) / RES)
            if not (0 <= cx < n and 0 <= cy < n):
                break
            if occ[cy, cx] > base:
                break
            seen[cy, cx] = True
            d += 0.5
    return float((seen & walk).sum()) / tot


def max_block_extent(g):
    """The longest bounding-box side of any mass in the map, per level, by 4-connected
    labelling of the same mask vectorise.blocks traces. The landmark is solved against this
    MEASURED number rather than against split_long's 34 m cap, because a block that wraps
    can have a bounding box far longer than its own OBB long axis - measured at 88 m on the
    first cave, which is why sizing against the cap failed verification by 0.64x."""
    built, lvl = g['built'], g['lvl']
    n = built.shape[0]
    best = 0.0
    for L in range(int(lvl.max()) + 1):
        m = built & (lvl == L)
        seen = np.zeros_like(m)
        idx = np.argwhere(m)
        for r0, c0 in idx:
            if seen[r0, c0]:
                continue
            stack, comp = [(r0, c0)], []
            seen[r0, c0] = True
            while stack:
                r, c = stack.pop()
                comp.append((r, c))
                for q in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
                    if 0 <= q[0] < n and 0 <= q[1] < n and m[q] and not seen[q]:
                        seen[q] = True
                        stack.append(q)
            if len(comp) * RES * RES < 40.0:
                continue
            rs = [p[0] for p in comp]
            cs = [p[1] for p in comp]
            best = max(best, (max(rs) - min(rs) + 1) * RES, (max(cs) - min(cs) + 1) * RES)
    return float(max(best, 10.0))


def tier1_mass(route, g, pl):
    """L1's tier clause needs a mass whose silhouette exceeds 1.6x every other in the map,
    appearing nowhere earlier in the series. Every other mass is bounded above by
    vectorise.split_long's own 34 m cap at BASE_STOREYS, so the landmark is SOLVED against
    that bound rather than chosen, then verified against the traced blocks after emission.

    It stands at the head of the terminus room with a walkable precinct round it, which is
    also what makes vectorise trace it as its own block instead of merging it into the
    street wall."""
    last = route['stations'][-1]
    ux, uy = math.cos(last['heading']), math.sin(last['heading'])
    bound = max_block_extent(g) * BASE_STOREYS * STOREY
    side = min(20.0, max(10.0, last['room']))
    storeys = 0
    while side <= 26.0:
        storeys = int(math.ceil(TIER1_FACTOR * bound / (side * STOREY)))
        if storeys <= STOREY_BAND[1]:
            break
        side += 2.0
    storeys = max(STOREY_BAND[0], min(STOREY_BAND[1], storeys))
    cx = last['ex'] + ux * (last['room'] + side * 0.5 + 3.0)
    cy = last['ey'] + uy * (last['room'] + side * 0.5 + 3.0)
    return dict(cx=float(cx), cy=float(cy), side=float(side), storeys=int(storeys),
                ux=float(ux), uy=float(uy), level=int(last['level']),
                silhouette=round(float(side * storeys * STOREY), 1),
                bound=round(float(bound), 1))


def place_tier1(g, pl, t1):
    """Stamp the landmark and its precinct. The precinct is walkable, which is what a
    monument in its own close is, and it is the gap that separates the trace."""
    X, Y = g['X'], g['Y']
    pre = np.zeros_like(g['walk'])
    stamp_rect(pre, t1['cx'], t1['cy'], t1['ux'], t1['uy'],
               t1['side'] + 5.2, t1['side'] + 5.2, X, Y)
    foot = np.zeros_like(g['walk'])
    stamp_rect(foot, t1['cx'], t1['cy'], t1['ux'], t1['uy'], t1['side'], t1['side'], X, Y)
    g['walk'] |= (pre & ~foot) & g['land']
    g['built'] = (g['built'] | foot) & g['land'] & ~g['walk']
    g['lvl'] = np.where((pre | foot) & g['land'], np.int16(t1['level']), g['lvl']).astype(np.int16)
    g['lvl'] = np.where(g['water'], np.int16(-1), g['lvl']).astype(np.int16)
    g['tier1_mask'] = foot
    return g


def stamp_occluder(g, pl, idea, thr):
    """Stage D's occlusion rule, applied to the plan before anything is measured: the hero
    mass crosses the principal threshold and the route is the only way through it. This is
    the element that hides the terminus, and THE-PICTURE section 2 item 2 is explicit that
    occlusion is chosen rather than incidental."""
    occl = np.zeros_like(g['walk'])
    ux, uy = math.cos(thr['heading']), math.sin(thr['heading'])
    depth = idea['occlusion']['depth_char'] * CHAR
    span = hero_span(thr)
    cx = (thr['x'] + thr['ex']) * 0.5
    cy = (thr['y'] + thr['ey']) * 0.5
    stamp_rect(occl, cx, cy, ux, uy, depth, span, g['X'], g['Y'])
    g['built'] = (g['built'] | (occl & ~g['walk'])) & g['land']
    g['occluder_mask'] = occl
    return g


def hero_span(thr):
    """The hero is the one piece of civil engineering the map is about, so it spans the
    throat and its own wing walls, not just the carriageway."""
    return max(10.0, thr['width'] * 4.0)


def gates(route, g, pl, series, t1, thr):
    """Every clause the prompt names, each read off the realised geometry in route order.

    G3 is reported and flagged: 'the running maximum must be non-decreasing' is vacuous
    for a running maximum, so the clause that actually bites is G2, the position of the
    global maximum. Saying so is cheaper than a gate that can never fail."""
    n = len(series)
    events = [i for i in range(1, n) if series[i] > series[i - 1] * REVEAL_RATIO]
    runmax, mono = -1.0, True
    for v in series:
        prev, runmax = runmax, max(runmax, v)
        mono = mono and runmax >= prev - 1e-9
    gmax = int(np.argmax(series))
    occ = occ_field(g)
    last = route['stations'][-1]
    tx, ty = last['ex'], last['ey']
    leaks = [s['i'] for s in route['stations'][:thr['i']]
             if sees(occ, s['level'], s['x'], s['y'], tx, ty, pl)]
    cover = [isovist_cover(occ, g['walk'], s['level'], s['x'], s['y'], pl)
             for s in route['stations']]
    widths = [s['width'] for s in all_stations(route)]
    spur_ok = all(sp['stations'][-1]['beat'] == 'reward' and sp['payload']
                  for sp in route['spurs'])
    climbs_at_throats = all(BEAT[s['beat']]['dlevel'] == 0 or s['kind'] == 'throat'
                            for s in all_stations(route) if s['beat'] in BEAT)
    out = dict(
        G1_reveal_events=dict(ok=2 <= len(events) <= 5, n=len(events), at=events),
        G2_global_max_final_fifth=dict(ok=gmax >= int(0.8 * (n - 1)), at=gmax, of=n - 1),
        G3_runmax_non_decreasing=dict(ok=mono, vacuous=True),
        G4_tier1_silhouette=dict(ok=bool(t1['silhouette'] >= TIER1_FACTOR * t1['bound']),
                                 sil=t1['silhouette'], need=round(TIER1_FACTOR * t1['bound'], 1)),
        G5_terminus_hidden_before_threshold=dict(ok=not leaks, leaks=leaks,
                                                 threshold_station=thr['i']),
        G6_single_file=dict(ok=min(widths) <= SINGLE_FILE_CHAR * CHAR + 1e-9,
                            min_m=round(min(widths), 2)),
        G7_elevation_at_throats=dict(ok=climbs_at_throats),
        G8_dead_ends_paid=dict(ok=spur_ok, spurs=len(route['spurs']),
                               payloads=[sp['payload'] for sp in route['spurs']]),
        G9_not_spent_in_one_frame=dict(ok=max(cover) < MAX_COVER,
                                       max_cover=round(max(cover), 3)),
    )
    out['ok'] = all(v['ok'] for k, v in out.items() if k.startswith('G'))
    out['series'] = [round(v, 1) for v in series]
    out['cover'] = [round(v, 3) for v in cover]
    return out


# ===========================================================================
# THE ENUMERATED REPAIR
# ===========================================================================
def realise(idea, turn_scale, room_scale, typ=None, side=None):
    """One candidate: beats -> route -> solid -> landmark -> occluder -> measured gates."""
    route = walk_beats(idea, turn_scale, room_scale)
    pl = plate(route)
    g = solid(route, idea, pl, typ, side)
    t1 = tier1_mass(route, g, pl)
    g = place_tier1(g, pl, t1)
    thr = principal_threshold(route)
    g = stamp_occluder(g, pl, idea, thr)
    series = sight_series(route, occ_field(g), pl)
    return dict(route=route, plate=pl, g=g, t1=t1, thr=thr, series=series,
                gates=gates(route, g, pl, series, t1, thr),
                knobs=(turn_scale, room_scale))


def search(idea, verbose=True, typ=None, side=None):
    """CONSTRUCTION-THEORY section 4 step 4 names the legal repairs in order: bend the
    route, raise the ground between, rotate the target, and only last insert an occluder.
    The first is a turn scale and the third is a room scale, both stepped through a fixed
    enumerated ladder in a fixed order, first pass wins. Nothing is nudged by eye, and
    every candidate's numbers are printed so the choice can be argued with."""
    tried = []
    for ts in TURN_LADDER:
        for rs in ROOM_LADDER:
            c = realise(idea, ts, rs, typ, side)
            gt = c['gates']
            fails = [k for k, v in gt.items() if k.startswith('G') and not v['ok']]
            tried.append(dict(turn=ts, room=rs, ok=gt['ok'], fails=fails,
                              events=gt['G1_reveal_events']['n'],
                              gmax=gt['G2_global_max_final_fifth']['at'],
                              leaks=len(gt['G5_terminus_hidden_before_threshold']['leaks']),
                              cover=gt['G9_not_spent_in_one_frame']['max_cover']))
            if verbose:
                print(f"    turn x{ts:<4} room x{rs:<4} events {tried[-1]['events']} "
                      f"gmax {tried[-1]['gmax']}/{len(c['series']) - 1} "
                      f"leaks {tried[-1]['leaks']} cover {tried[-1]['cover']:.2f} "
                      f"{'PASS' if gt['ok'] else 'fail ' + ','.join(f[:2] for f in fails)}")
            if gt['ok']:
                c['tried'] = tried
                return c
    raise ComposeError(
        'no candidate in the enumerated ladder satisfies the route gates for '
        f"{idea['id']}. Tried {len(tried)} combinations; the failures were "
        + '; '.join(f"turn {t['turn']} room {t['room']}: {','.join(t['fails'])}"
                    for t in tried))


# ===========================================================================
# STAGE D - THE HERO, AND THE CAUSES THAT MAKE IT ARGUABLE
# ===========================================================================
BAY_PROTO = {'cave': 'passage_bay', 'dungeon': 'passage_bay', 'town': 'street_bay',
             'interior': 'street_bay', 'coast': 'quay_bay', 'island': 'quay_bay',
             'arena': 'row_bay', 'stadium': 'row_bay'}
ACROSS_SLOTS = ('span', 'span_left', 'span_right')


def hero_assembly(idea, thr):
    """The organising idea instantiated as an assembly of its own named sub-parts, on the
    frame of the principal threshold.

    THE-PICTURE section 3 L1: the organising object is never a mesh, it is eight to fifteen
    authored sub-parts. The slot table is closed, so a part can only land somewhere a slot
    already names, and a second part in an occupied slot is pushed along the route by 0.8 m
    rather than dropped on top of the first."""
    span = hero_span(thr)
    ux, uy = math.cos(thr['heading']), math.sin(thr['heading'])
    px, py = -uy, ux
    ox = (thr['x'] + thr['ex']) * 0.5
    oy = (thr['y'] + thr['ey']) * 0.5
    used, counter, out = {}, {}, []
    for part, slot in idea['hero']:
        fn = part.split('.')[1]
        specs = ([(af, 0.50, 0) for af in INTERVAL_ALONG] if slot == 'interval'
                 else [SLOT[slot]])
        for af, cf, dl in specs:
            rep = used.get(slot, 0)
            used[slot] = rep + 1
            k = counter.get(fn, 0)
            counter[fn] = k + 1
            along = af * span + 0.8 * rep
            across = cf * span
            out.append(dict(
                part=part, slot=slot,
                pos=[round(ox + ux * along + px * across, 2),
                     round(oy + uy * along + py * across, 2),
                     round((thr['level'] + dl) * LEVEL, 2)],
                rot=round(thr['heading'] + (math.pi / 2 if slot in ACROSS_SLOTS else 0.0), 4),
                obj=f'{fn}_{k}', prototype=part,
                occluder=(part == idea['occlusion']['by'])))
    return out


def cause_registry(idea, route, hero, t1, scene):
    """The L2 record. A deviation may only exist because a NAMED piece of real geometry is
    in the same frame as it, so every bend past DEVIATION_DEG gets an outcrop, fault plane
    or older structure planted on the OUTSIDE of that bend, and the straight stations are
    registered as the undeviated siblings the law counts.

    CONSTRUCTION-THEORY section 1.2 is explicit that this is legitimate: a fictional
    outcrop that the wall visibly bends around, in the same shot as the bend, delivers the
    entire payoff with no solve at all - what fails is a reason that lives only in the
    solver. The direction of authorship is not what the viewer reads."""
    reg = OC.Registry(scene)
    proto = BAY_PROTO[idea['type']]
    kind = CAUSE_KIND[idea['type']]
    for h in hero:
        reg.element(h['prototype'], h['pos'], h['obj'], rot=h['rot'])
    reg.element('landmark', [t1['cx'], t1['cy'], t1['level'] * LEVEL],
                'tier1_landmark', id='landmark#tier1')
    bends, straights = [], []
    for s in route['stations']:
        (bends if abs(s['turn']) >= DEVIATION_DEG else
         straights if abs(s['turn']) < STRAIGHT_DEG else []).append(s)
    for s in straights:
        reg.element(proto, [s['x'], s['y'], s['level'] * LEVEL], f'{proto}_{s["i"]}')
    for s in bends:
        ux, uy = math.cos(s['heading']), math.sin(s['heading'])
        px, py = -uy, ux
        side = -1.0 if s['turn'] > 0 else 1.0        # the outside of the bend
        r = 1.3 * CHAR
        cx = s['x'] + px * side * (s['width'] * 0.5 + r)
        cy = s['y'] + py * side * (s['width'] * 0.5 + r)
        c = reg.cause(f'{kind}_{s["i"]}', kind, [cx, cy, s['level'] * LEVEL], r,
                      f'{kind}_{s["i"]}',
                      note=f"the {proto} at station {s['i']} turns {s['turn']:.0f} deg round it")
        el = reg.element(proto, [s['x'], s['y'], s['level'] * LEVEL], f'{proto}_{s["i"]}')
        reg.deviate(el, c, 'rotate', math.radians(s['turn']))
    return reg


# ===========================================================================
# STAGE E - EMIT
# ===========================================================================
def neighbour_falls(g):
    """ED-2 and the quay rule, off the grid: a walkable edge with a fall beside it needs a
    guard, and land meeting water is a quay. Both are consequences, not decisions."""
    lvl, walk, water, land = g['lvl'], g['walk'], g['water'], g['land']
    drops = np.zeros_like(walk)
    quay = np.zeros_like(walk)
    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nl = np.roll(np.roll(lvl, dy, 0), dx, 1)
        nw = np.roll(np.roll(water, dy, 0), dx, 1)
        nland = np.roll(np.roll(land, dy, 0), dx, 1)
        drops |= walk & land & (((nl < lvl) & nland) | nw)
        quay |= land & nw
    return drops, quay


def grids(g):
    lvl = g['lvl'].astype(np.int16)
    z = lvl.astype(np.float64) * LEVEL
    z[g['water']] = np.nan
    drops, quay = neighbour_falls(g)
    walls = np.zeros_like(g['built'])
    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        walls |= g['built'] & ~np.roll(np.roll(g['built'], dy, 0), dx, 1)
    street = g['walk'] | g.get('alleys', np.zeros_like(g['walk']))
    return dict(z=z, lvl=lvl, built=g['built'], street=street, water=g['water'],
                walk=g['walk'], walls=walls, drops=drops, quay=quay)


WELD_TOL_M = 1e-4


def weld(mesh, tol=WELD_TOL_M):
    """Merge coincident verts and reindex the faces, before ops_solid sees the mesh.

    MEASURED, and the reason this exists rather than a relaxed gate: a 40 m rect prism is
    exact and its 24 verts collapse to 8 at a 1e-4 weld and to 20 at ops_solid's own 1e-6
    default, so the shell arrives OPEN (22 boundary edges) and carve() rejects it - which is
    the gate being right. Perturbing the rect off axis does not help (18v), so the effect is
    scale, not alignment. The fix belongs in the caller: hand carve a shell that is already
    welded and its 1e-6 pass has nothing left to do."""
    q = 1.0 / tol
    key, remap, verts = {}, [], []
    for v in mesh.v:
        k = (round(v[0] * q), round(v[1] * q), round(v[2] * q))
        if k not in key:
            key[k] = len(verts)
            verts.append(tuple(float(x) for x in v))
        remap.append(key[k])
    out = _g.Mesh()
    out.v = verts
    for f, mat in zip(mesh.f, mesh.m):
        nf = []
        for i in f:
            j = remap[i]
            if not nf or nf[-1] != j:
                nf.append(j)
        if len(nf) > 2 and nf[0] == nf[-1]:
            nf.pop()
        if len(nf) >= 3:
            out.f.append(tuple(nf))
            out.m.append(mat)
        else:
            out.dropped += 1
    return out


def carve_check(c, geom):
    """The one operation the pipeline never had. THE-PICTURE section 6: extrusion is
    monotonic in Z, so it cannot produce a hole, a ceiling or an underside at all. Here the
    plate is a real closed solid and the traced walk surface is the tool, so the streets are
    SLOTS through one continuous mass rather than gaps between boxes.

    The measurement that proves it is ops_solid.undersides: an extrusion has exactly one
    down-facing face, its own bottom cap, so any count above zero above the walk surface is
    non-monotonicity in Z. Needs Blender; when bpy is absent this reports that it did not
    run rather than pretending."""
    if not getattr(OS, 'bpy', None):
        return dict(ran=False, why='bpy unavailable, so the boolean was not attempted')
    pl, g = c['plate'], c['g']
    clear = 2.2 * CHAR                               # headroom over the walk surface
    # one extra LEVEL of solid above the highest passage, so every tool leaves a roof
    # rather than cutting clean through - otherwise the undersides count is zero and the
    # measurement proves nothing
    top = float(g['lvl'].max()) * LEVEL + clear + LEVEL
    if g['side'] == 'mass':
        # the solid is the LAND BODY, and the walk surface notched out of it is literally
        # THE-PICTURE's dock notch: a rectangular basin subtracted from stone quays
        body = max(((abs(_area2(lp)), lp) for lp in geom.get('shore', [])), default=None)
        if body is None:
            return dict(ran=True, ok=False, why='no traced shore loop to carve')
        outline = body[1]
    else:
        outline = [(pl['ox'], pl['oy']), (pl['ox'] + pl['span'], pl['oy']),
                   (pl['ox'] + pl['span'], pl['oy'] + pl['span']),
                   (pl['ox'], pl['oy'] + pl['span'])]
    plate_m = _g.Mesh()
    _g.prism(plate_m, outline, -LEVEL, top, mat='rock', cap_top=True, cap_bot=True)
    plate_m = weld(plate_m)
    v0 = abs(OS.volume(plate_m))
    loops = sorted([(abs(_area2(lp)), lp, w['level'])
                    for w in geom.get('ways', []) for lp in w['loops']], reverse=True)[:6]
    cut, faces = 0, 0
    for _, lp, L in loops:
        tool = _g.Mesh()
        _g.prism(tool, lp, L * LEVEL - 0.3, L * LEVEL + clear, mat='void',
                 cap_top=True, cap_bot=True)
        tool = weld(tool)
        try:
            # the boolean RESULT has to be welded too before it becomes the next operand,
            # for exactly the reason above: measured 62 boundary edges on the second pass
            plate_m = weld(OS.carve(plate_m, tool, tool_mat='reveal'))
            cut += 1
        except Exception as e:                       # a failed boolean is reported, not hidden
            return dict(ran=True, ok=False, cut=cut, why=f'{type(e).__name__}: {e}')
    v1 = abs(OS.volume(plate_m))
    und = OS.undersides(plate_m, above_z=0.5)
    return dict(ran=True, ok=True, tools=cut, volume_before=round(v0, 1),
                volume_after=round(v1, 1), removed_m3=round(v0 - v1, 1),
                faces=len(plate_m.f), undersides_above_walk=len(und),
                note='undersides above the walk surface are the ceiling the carve left; '
                     'an extrusion has none')


def _area2(poly):
    a = 0.0
    for i in range(len(poly)):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % len(poly)]
        a += x0 * y1 - x1 * y0
    return a / 2.0


def _point_in(x, y, poly):
    inside = False
    n = len(poly)
    for i in range(n):
        (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % n]
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) / (y1 - y0) * (x1 - x0):
            inside = not inside
    return inside


def verify_tier1(geom, t1):
    """L1's tier clause, checked against the blocks vectorise actually traced rather than
    against the bound the landmark was sized with."""
    worst, worst_n = 0.0, 0
    for b in geom.get('blocks', []):
        pts = b['pts']
        if _point_in(t1['cx'], t1['cy'], pts):       # the landmark's own block, not a rival
            continue
        w = max(p[0] for p in pts) - min(p[0] for p in pts)
        h = max(p[1] for p in pts) - min(p[1] for p in pts)
        worst = max(worst, max(w, h) * BASE_STOREYS * STOREY)
        worst_n += 1
    ratio = (t1['silhouette'] / worst) if worst else float('inf')
    return dict(ok=bool(ratio >= TIER1_FACTOR), ratio=round(float(ratio), 2),
                tier1_silhouette=t1['silhouette'], next_largest=round(float(worst), 1),
                blocks_measured=worst_n)


def emit(brief, sel, c, hero, reg, do_carve, root=None):
    """Everything downstream already consumes geom.json + vectors.json, so the composer
    writes the grids and lets vectorise.py trace them. That is deliberate: the builder only
    ever sees polygons, which is what makes per-cell crumb terrain structurally impossible
    rather than merely avoided."""
    root = root or HERE
    idea = sel['idea']
    slug = ''.join(ch if ch.isalnum() else '-' for ch in brief.lower()).strip('-')
    sd = os.path.join(root, 'place', slug, 'spec')
    os.makedirs(sd, exist_ok=True)
    pl, g, t1 = c['plate'], c['g'], c['t1']
    gr = grids(g)
    levels = int(gr['lvl'].max()) + 1
    spec = dict(place=slug, res=RES, span_m=pl['span'], level_step_m=LEVEL, levels=levels,
                base_z=0.0, walkfrac=round(float(gr['walk'].mean()), 6),
                gates={k: bool(v['ok']) for k, v in c['gates'].items() if k.startswith('G')})
    json.dump(spec, open(os.path.join(sd, 'spec.json'), 'w'), indent=1)
    np.savez_compressed(os.path.join(sd, 'grids.npz'), **gr)
    geom = VEC.build(sd)

    # the landmark is the only surveyed building: build_place reads storeys from here, and
    # everything else falls back to its own BASE_STOREYS default
    half = t1['side'] / 2
    ux, uy = t1['ux'], t1['uy']
    px, py = -uy, ux
    foot = [[round(t1['cx'] + ux * half * sx + px * half * sy, 2),
             round(t1['cy'] + uy * half * sx + py * half * sy, 2)]
            for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    json.dump(dict(span_m=pl['span'], buildings=[dict(pts=foot, storeys=t1['storeys'])],
                   streets=[], quays=[]),
              open(os.path.join(sd, 'vectors.json'), 'w'), indent=1)

    route = c['route']
    json.dump(dict(
        brief=brief, idea=idea['id'], type=sel['type'], side=g['side'],
        origin=[round(pl['ox'], 2), round(pl['oy'], 2)], span_m=pl['span'],
        polyline=route_polyline(route),
        # ready to paste: frameaudit.py takes the spine as one --route argument, and the
        # audit is the instrument that decides whether the built map kept the journey
        frameaudit_route=';'.join(','.join(f'{v:g}' for v in p)
                                  for p in route_polyline(route)),
        stations=[dict(i=s['i'], beat=s['beat'], x=round(s['x'], 2), y=round(s['y'], 2),
                       z=round(s['level'] * LEVEL, 2), level=s['level'],
                       width_m=round(s['width'], 2), room_m=round(s['room'], 2),
                       turn_deg=round(s['turn'], 1), kind=s['kind'],
                       target_visvol=round(c['series'][s['i']], 1))
                  for s in route['stations']],
        spurs=[dict(payload=sp['payload'],
                    polyline=[[round(x['x'], 2), round(x['y'], 2),
                               round(x['level'] * LEVEL, 2)] for x in sp['stations']]
                    + [[round(sp['stations'][-1]['ex'], 2), round(sp['stations'][-1]['ey'], 2),
                        round(sp['stations'][-1]['level'] * LEVEL, 2)]],
                    beats=[x['beat'] for x in sp['stations']])
               for sp in route['spurs']],
        principal_threshold=c['thr']['i'], target_visvol=[round(v, 1) for v in c['series']],
        gates=c['gates']),
        open(os.path.join(sd, 'route.json'), 'w'), indent=1)

    carve = carve_check(c, geom) if do_carve else dict(ran=False, why='--carve not asked for')
    t1v = verify_tier1(geom, t1)
    json.dump(dict(
        brief=brief, selected=dict(idea=idea['id'], type=sel['type'], side=g['side'],
                                   keyword_hits=sel['keyword_hits'],
                                   type_hits=sel['type_hits'],
                                   by_type_only=sel['by_type_only']),
        beats=list(idea['beats']), occlusion=idea['occlusion'],
        knobs=dict(turn_scale=c['knobs'][0], room_scale=c['knobs'][1]),
        ladder=c['tried'], hero=hero, tier1=dict(t1, **{'verified': t1v}),
        solid=dict(side=g['side'], plate_span_m=pl['span'], levels=levels,
                   walk_cells=int(gr['walk'].sum()), built_cells=int(gr['built'].sum()),
                   water_cells=int(gr['water'].sum())),
        carve=carve,
        registry=dict(path=os.path.relpath(OC.registry_path(reg.scene, root), root),
                      elements=len(reg.elements), causes=len(reg.causes),
                      deviations=len(reg.deviations)),
        contract='R2 needs the builder to name its objects hero[].obj and causes[].obj; '
                 'build_place.py currently names by material, so R2 cannot pass downstream '
                 'until that is honoured'),
        open(os.path.join(sd, 'compose.json'), 'w'), indent=1)
    rp = reg.save(OC.registry_path(reg.scene, root))
    return dict(spec_dir=sd, geom=geom, carve=carve, tier1=t1v, registry=rp, spec=spec)


def compose(brief, type_override=None, do_carve=False, verbose=True):
    sel = select(brief, type_override)
    idea = sel['idea']
    if verbose:
        print(f"[A] PROGRAM   {idea['id']}  type={sel['type']} side={idea['side']}  "
              f"keywords={sel['keyword_hits'] or '-'} type_words={sel['type_hits'] or '-'}"
              f"{'  (SELECTED BY TYPE ALONE, no keyword evidence)' if sel['by_type_only'] else ''}")
        print(f"              beats: {' '.join(idea['beats'])}")
        print(f"              occludes {idea['occlusion']['hides']} with "
              f"{idea['occlusion']['by']} - {idea['occlusion']['note']}")
        print('[B] ROUTE     enumerated repair, first pass wins:')
    c = search(idea, verbose=verbose, typ=sel['type'], side=sel['side'])
    route = c['route']
    thr = c['thr']
    hero = hero_assembly(idea, thr)
    scene = 'compose_' + ''.join(ch if ch.isalnum() else '_' for ch in brief.lower())
    reg = cause_registry(idea, route, hero, c['t1'], scene)
    probs, notes = reg.structural_check()
    if probs:
        raise ComposeError('the cause registry can never satisfy R2 in any frame: '
                           + '; '.join(probs))
    out = emit(brief, sel, c, hero, reg, do_carve)
    if verbose:
        gt = c['gates']
        print(f"              {len(route['stations'])} stations, {len(route['spurs'])} spur(s), "
              f"turn x{c['knobs'][0]} room x{c['knobs'][1]}")
        print(f"              target visvol {gt['series']}")
        print(f"[C] SOLID     side={c['g']['side']} plate {c['plate']['span']:.0f} m "
              f"levels {out['spec']['levels']} walk {out['spec']['walkfrac'] * 100:.1f}% "
              f"{len(out['geom']['blocks'])} blocks "
              f"stairs {len(out['geom']['stairs'])} quays {len(out['geom']['quays'])} "
              f"parapets {len(out['geom']['parapets'])}")
        print(f"[D] HERO      {len(hero)} instances of {len(idea['hero'])} named parts at "
              f"station {thr['i']} ({thr['beat']}); tier-1 {c['t1']['side']:.1f} m x "
              f"{c['t1']['storeys']} storeys, silhouette ratio {out['tier1']['ratio']} "
              f"vs next {out['tier1']['next_largest']} m2 "
              f"{'OK' if out['tier1']['ok'] else 'FAIL'}")
        print(f"              causes {len(reg.causes)} deviations {len(reg.deviations)} "
              f"elements {len(reg.elements)}; structural problems none")
        print(f"[E] EMIT      {os.path.relpath(out['spec_dir'], HERE)}: spec.json grids.npz "
              f"geom.json vectors.json route.json compose.json")
        print(f"              {os.path.relpath(out['registry'], HERE)}")
        print(f"              carve: {out['carve']}")
        print('    GATES     ' + '  '.join(
            f"{k.split('_')[0]}{'+' if v['ok'] else '-'}" for k, v in gt.items()
            if k.startswith('G')) + f"   ALL {'PASS' if gt['ok'] else 'FAIL'}")
    return out


def _selftest():
    """The gates must actually reject. A composer that accepts everything is decoration.

    Also exercises the third L5 branch: no catalogue idea is sightline-authored, because
    the observed list in THE-PICTURE section 2 contains no arena, so the branch is reached
    by declaring the type and is reported as such rather than left as dead code."""
    print(f'catalogue: {N_IDEAS} ideas gated at import')
    bad = []
    for label, fn in (
            ('empty brief', lambda: select('')),
            ('nonsense brief', lambda: select('qqq zzz')),
            ('type off the L5 table', lambda: select('town', 'swamp')),
    ):
        try:
            fn()
            bad.append(label)
        except ComposeError:
            print(f'  rejected: {label}')
    if bad:
        raise ComposeError(f'these should have been rejected and were not: {bad}')
    sel = select('ring arena', 'arena')
    c = realise(sel['idea'], 1.2, 1.0, 'arena')
    fails = [k for k, v in c['gates'].items() if k.startswith('G') and not v['ok']]
    print(f"  sightline branch: {sel['idea']['id']} forced to type arena -> "
          f"side={c['g']['side']}, {c['g'].get('rows')} rake rows solved from the C-value "
          f"recurrence, levels 0..{int(c['g']['lvl'].max())}")
    print(f"    gates {'PASS' if not fails else 'fail ' + ','.join(fails)}. G4 fails for "
          f"every one of the 25 ladder candidates and this is not a bug in the ladder: the "
          f"bowl's own mass IS the largest silhouette in an arena, so L1's tier-1 clause "
          f"has no satisfiable reading there. No catalogue idea is sightline-authored "
          f"either, because THE-PICTURE section 2's observed list contains no arena.")
    # the shuffle test from CONSTRUCTION-THEORY 6.2: permute the station order and the
    # order-sensitive series must move. A metric that survives a shuffle is not measuring
    # composition.
    sel = select('harbour town')
    c = realise(sel['idea'], 1.0, 1.0)
    base = c['series']
    sh = list(c['route']['stations'])
    sh = sh[::-1]
    for n, s in enumerate(sh):
        s['i'] = n
    c2 = dict(c, route=dict(c['route'], stations=sh))
    ser2 = sight_series(c2['route'], occ_field(c['g']), c['plate'])
    moved = sum(1 for a, b in zip(base, ser2) if abs(a - b) > 1e-6)
    print(f'  shuffle test: {moved}/{len(base)} station values move when the route order '
          f"is reversed{'' if moved else ' - THE SERIES IS PERMUTATION-INVARIANT, DISCARD IT'}")
    if not moved:
        raise ComposeError('the sight series did not move under a station permutation')
    return True


def arg(n, d=None):
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
    return argv[argv.index(n) + 1] if n in argv else d


def flag(n):
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
    return n in argv


if __name__ == '__main__':
    if flag('--selftest'):
        _selftest()
    else:
        briefs = [b for b in (arg('--brief'), arg('--brief2')) if b] or ['harbour town']
        for b in briefs:
            print('=' * 78)
            print(f'BRIEF: {b!r}')
            print('=' * 78)
            compose(b, type_override=arg('--type'), do_carve=flag('--carve'))
