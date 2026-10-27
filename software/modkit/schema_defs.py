"""JSON Schema（Draft 2020-12）定义：世界 v2、管网 v1。

这些 schema 是“结构/单位”契约，不替代 `World.validate()` 的几何/物理校验。
查看器/第三方可以用它做编辑器补全；服务端仍会跑 Python 校验。
"""

from __future__ import annotations

SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"


def _vec(n: int) -> dict:
    return {"type": "array", "items": {"type": "number"}, "minItems": n, "maxItems": n}


def _id() -> dict:
    return {"type": "string", "minLength": 1, "maxLength": 80}


def world_schema() -> dict:
    object_props = {
        "id": _id(), "type": {"enum": ["box", "cylinder", "sphere", "plane", "mesh", "heightfield"]},
        "name": {"type": "string"},
        "position": _vec(3), "rotation": _vec(3), "size": _vec(3),
        "radius": {"type": "number", "exclusiveMinimum": 0},
        "height": {"type": "number", "exclusiveMinimum": 0},
        "color": {"type": "string"}, "opacity": {"type": "number", "minimum": 0, "maximum": 1},
        "collider": {"enum": ["box", "mesh", "none"]},
        "semantic": {"type": "string"}, "source": {"type": "string"},
        "heights": {"type": "array", "minItems": 2,
                    "items": {"type": "array", "minItems": 2, "items": {"type": "number"}}},
        "metadata": {"type": "object"},
    }
    fluid_props = {
        "id": _id(), "type": {"enum": ["pool", "tank", "pipe", "puddle", "rain", "reservoir"]},
        "fluid": {"type": "string", "minLength": 1}, "name": {"type": "string"},
        "position": _vec(3), "size": _vec(3),
        "radius": {"type": "number", "exclusiveMinimum": 0},
        "height": {"type": "number", "exclusiveMinimum": 0},
        "footprint": {"type": "array", "minItems": 3,
                      "items": {"type": "array", "items": {"type": "number"},
                                "minItems": 2, "maxItems": 2}},
        "level": {"type": "number", "minimum": 0, "maximum": 1},
        "temperature_c": {"type": "number"},
        "salinity_ppt": {"type": "number", "minimum": 0},
        "volume_m3": {"type": "number", "minimum": 0},
        "color": {"type": "string"}, "metadata": {"type": "object"},
    }
    obj = {"type": "object", "required": ["id", "type"],
           "properties": object_props, "additionalProperties": True,
           "allOf": [
               {"if": {"properties": {"type": {"const": "box"}}},
                "then": {"required": ["size"]}},
               {"if": {"properties": {"type": {"const": "cylinder"}}},
                "then": {"required": ["radius", "height"]}},
               {"if": {"properties": {"type": {"const": "sphere"}}},
                "then": {"required": ["radius"]}},
               {"if": {"properties": {"type": {"const": "plane"}}},
                "then": {"required": ["size"]}},
               {"if": {"properties": {"type": {"const": "mesh"}}},
                "then": {"required": ["source"]}},
               {"if": {"properties": {"type": {"const": "heightfield"}}},
                "then": {"anyOf": [{"required": ["source"]}, {"required": ["heights"]}]}},
           ]}
    fluid = {"type": "object", "required": ["id", "type", "fluid", "position", "size"],
             "properties": fluid_props, "additionalProperties": True}
    return {
        "$schema": SCHEMA_DRAFT, "$id": "https://github.com/gh503/robot-modkit/schema/world-2.json",
        "title": "modkit world v2", "type": "object",
        "required": ["schema", "name", "units", "objects", "fluids"],
        "properties": {
            "schema": {"const": "modkit.world/2"},
            "name": {"type": "string", "minLength": 1, "maxLength": 200},
            "description": {"type": "string"},
            "units": {"const": "m"},
            "gravity": {"type": "number", "exclusiveMinimum": 0, "maximum": 50},
            "environment": {"type": "string"},
            "objects": {"type": "array", "items": obj},
            "fluids": {"type": "array", "items": fluid},
            "robot": {"type": "object",
                      "properties": {"assembly": {"type": "string"}, "position": _vec(3),
                                     "yaw_deg": {"type": "number"}, "task": {"type": "string"}},
                      "additionalProperties": True},
            "sensors": {"type": "array", "items": {
                "type": "object", "required": ["id", "type", "position"],
                "properties": {"id": _id(), "type": {"type": "string"}, "position": _vec(3),
                               "target": {"type": "string"}, "unit": {"type": "string"}},
                "additionalProperties": True}},
            "custom_fluids": {"type": "array", "items": {"type": "object"}},
            "lighting": {"type": "object"},
            "georeference": {"type": ["object", "null"]},
            "metadata": {"type": "object"},
        },
        "additionalProperties": True,
    }


def network_schema() -> dict:
    node = {"type": "object", "required": ["id"],
            "properties": {"id": _id(), "elevation_m": {"type": "number"},
                           "head_m": {"type": ["number", "null"]},
                           "demand_m3_s": {"type": "number", "minimum": 0},
                           "kind": {"enum": ["junction", "reservoir", "tank"]}},
            "additionalProperties": True}
    pipe = {"type": "object", "required": ["id", "from_node", "to_node", "length_m", "diameter_m"],
            "properties": {"id": _id(), "from_node": _id(), "to_node": _id(),
                           "length_m": {"type": "number", "exclusiveMinimum": 0},
                           "diameter_m": {"type": "number", "exclusiveMinimum": 0},
                           "roughness_m": {"type": "number", "minimum": 0},
                           "minor_k": {"type": "number", "minimum": 0},
                           "status": {"enum": ["open", "closed"]}},
            "additionalProperties": True}
    pump = {"type": "object", "required": ["id", "from_node", "to_node", "curve"],
            "properties": {"id": _id(), "from_node": _id(), "to_node": _id(),
                           "curve": {"type": "array", "minItems": 2,
                                     "items": _vec(2)},
                           "efficiency": {"type": "number", "exclusiveMinimum": 0, "maximum": 1},
                           "speed": {"type": "number", "exclusiveMinimum": 0},
                           "status": {"enum": ["open", "closed"]}},
            "additionalProperties": True}
    return {
        "$schema": SCHEMA_DRAFT, "$id": "https://github.com/gh503/robot-modkit/schema/network-1.json",
        "title": "modkit network v1", "type": "object",
        "required": ["schema", "nodes", "pipes", "pumps"],
        "properties": {"schema": {"const": "modkit.network/1"},
                       "name": {"type": "string"}, "fluid": {"type": "string"},
                       "nodes": {"type": "array", "items": node, "minItems": 2},
                       "pipes": {"type": "array", "items": pipe},
                       "pumps": {"type": "array", "items": pump},
                       "metadata": {"type": "object"}},
        "additionalProperties": True,
    }


__all__ = ["SCHEMA_DRAFT", "world_schema", "network_schema"]
