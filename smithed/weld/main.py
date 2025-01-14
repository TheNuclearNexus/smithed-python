from contextlib import contextmanager, suppress
from functools import partial
from importlib import resources
from typing import Iterable, Literal
from zipfile import ZipFile

from beet import Context, JsonFile, PluginError, ProjectConfig, run_beet, subproject
from beet.core.utils import FileSystemPath, JsonDict
from jinja2 import Template

from . import merge_policies

DESCRIPTION = "Merged by Smithed Weld"
FABRIC_MOD_TEMPLATE = Template(
    (resources.files("weld") / "fabric.mod.json.j2").read_text()
)


@contextmanager
def run_weld(
    packs: Iterable[str] | Iterable[ZipFile],
    config: FileSystemPath | ProjectConfig | JsonDict = {},
    directory: FileSystemPath | None = None,
    pack_types: list[Literal["data_pack", "resource_pack"]] = ["data_pack"],
    use_overrides: bool = False
):
    if type(config) is dict:
        config |= {
            "output": "dist",
        }
        for pack_type in pack_types:
            config[pack_type] = {
                "zipped": True,
                "description": DESCRIPTION,
                "name": "welded-pack",
            }

    with run_beet(config, directory=directory) as ctx:
        ctx.require("beet.contrib.model_merging")

        if use_overrides:
            ctx.require(merge_policies.setup)

        ctx.require(partial(load_packs, packs=list(packs), pack_types=pack_types))

        if use_overrides:
            ctx.require(merge_policies.beet_default)

        yield ctx


def load_packs(
    ctx: Context,
    packs: list[str] | list[ZipFile],
    pack_types: list[Literal["data_pack", "resource_pack"]],
):
    # ctx.require("weld.setup")
    for pack in packs:
        for pack_type in pack_types:
            match pack:
                case str(name):
                    ctx.require(
                        subproject(
                            {
                                "require": ["beet.contrib.unknown_files"],
                                pack_type: {"load": name},
                                "pipeline": ["weld.print_pack_name"],
                            }
                        )
                    )
                case ZipFile() as file:
                    default_id = ''.join(file.filename.split('\\')[-1].split('.')[:-1])
                    if pack_type == "data_pack":
                        ctx.data.mcmeta.data.setdefault("id", default_id)
                        ctx.data.load(file)
                    else:
                        ctx.assets.mcmeta.data.setdefault("id", default_id)
                        ctx.assets.load(file)

    if len(pack_types) > 1:
        JsonFile(
            FABRIC_MOD_TEMPLATE.render(
                pack_hash=hash(tuple(packs)),
                pack_names=[
                    pack.filename if type(pack) is ZipFile else pack for pack in packs
                ],
                mc_version=ctx.minecraft_version,
            )
        )
        ctx.require(partial(add_fabric_mod_json, packs=packs))


def add_fabric_mod_json(ctx: Context, packs: list[str] | list[ZipFile]):
    ctx.data.extra["fabric.mod.json"] = JsonFile(
        FABRIC_MOD_TEMPLATE.render(
            packs=packs,
            pack_names=[
                pack.filename if type(pack) is ZipFile else pack for pack in packs
            ],
            mc_version=ctx.minecraft_version,
        )
    )


def print_pack_name(ctx: Context):
    """Prints the merging pack name"""

    if not ctx.data and not ctx.assets:
        return

    print(
        f"Merging {'data' if ctx.data else 'resource'} pack:"
        f" {ctx.data.name or ctx.assets.name or 'Unknown'}"
    )
