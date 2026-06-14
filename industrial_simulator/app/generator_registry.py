from __future__ import annotations
from app.generators.base import DomainGenerator
from app.generators.petroleum_pipeline import PetroleumPipelineGenerator
from app.generators.eaf_melting import EafMeltingGenerator
from app.generators.gas_pipeline import GasPipelineGenerator
from app.generators.rotary_equipment import RotaryEquipmentGenerator
from app.generators.power_plant import PowerPlantGenerator
from app.generators.steel_blast_furnace import BlastFurnaceGenerator
from app.generators.steel_coke_oven import CokeOvenGenerator
from app.generators.steel_dri_plant import DriPlantGenerator
from app.generators.steel_lrf import LrfGenerator
from app.generators.steel_ccm import CcmGenerator
from app.generators.steel_rolling_mill import RollingMillGenerator
from app.models import GeneratorSummary

_GENERATORS: dict[str, DomainGenerator] = {
    "petroleum_pipeline": PetroleumPipelineGenerator(),
    "eaf_melting": EafMeltingGenerator(),
    "gas_pipeline": GasPipelineGenerator(),
    "rotary_equipment": RotaryEquipmentGenerator(),
    "power_plant": PowerPlantGenerator(),
    "steel_blast_furnace": BlastFurnaceGenerator(),
    "steel_coke_oven": CokeOvenGenerator(),
    "steel_dri_plant": DriPlantGenerator(),
    "steel_lrf": LrfGenerator(),
    "steel_ccm": CcmGenerator(),
    "steel_rolling_mill": RollingMillGenerator(),
}


def list_generators() -> list[GeneratorSummary]:
    return [GeneratorSummary(domain_id=g.domain_id, display_name=g.display_name, description=g.description) for g in _GENERATORS.values()]


def get_generator(domain_id: str) -> DomainGenerator:
    if domain_id not in _GENERATORS:
        raise KeyError(f"Unknown generator: {domain_id}")
    return _GENERATORS[domain_id]
