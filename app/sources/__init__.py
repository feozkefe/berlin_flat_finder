from app.sources.immoscout import ImmoScoutSource
from app.sources.kleinanzeigen import KleinanzeigenSource
from app.sources.wg_gesucht import WgGesuchtSource

SOURCE_MAP = {
    "wg_gesucht": WgGesuchtSource,
    "kleinanzeigen": KleinanzeigenSource,
    "immoscout": ImmoScoutSource,
}
