"""Constants shared by the maker package."""

# Limits enforced while loading user component files.
MAX_FILE_BYTES = 32768
MAX_DOCS_PER_FILE = 20
MAX_USER_FILES = 200
MAX_COMPONENTS = 200

# Limits enforced while validating one component.
MAX_PARAMS = 8
MAX_INPUTS = 16
MAX_OUTPUTS = 12
MAX_LAYOUT_ITEMS = 16
MAX_DATA_KEYS = 8
MAX_STRING = 1024
FOR_EACH_MAX = 8
MAX_WIDGETS = 32

# Allow-lists for service data templates; see maker/templates.py.
DATA_TEMPLATE_FILTERS = frozenset(
    {
        "abs",
        "bool",
        "capitalize",
        "count",
        "d",
        "default",
        "first",
        "float",
        "int",
        "last",
        "length",
        "lower",
        "max",
        "min",
        "round",
        "string",
        "title",
        "trim",
        "upper",
    }
)
DATA_TEMPLATE_TESTS = frozenset(
    {
        "boolean",
        "defined",
        "false",
        "float",
        "integer",
        "none",
        "number",
        "string",
        "true",
        "undefined",
    }
)

# Template features left out of Components; see sandbox.py and maker/templates.py.
# Regular expressions can backtrack for exponential time inside one call that
# cannot be interrupted. pack and unpack build byte strings of any size from a
# format; format, format_map, translate and expandtabs build text whose size
# comes from an argument. apply and as_function call a callable directly,
# skipping the sandbox's call checks, and lipsum generates text of any length.
UNAVAILABLE_FILTERS = frozenset(
    {
        "apply",
        "as_function",
        "format",
        "pack",
        "regex_findall",
        "regex_findall_index",
        "regex_match",
        "regex_replace",
        "regex_search",
        "unpack",
    }
)
UNAVAILABLE_TESTS = frozenset({"apply", "match", "search"})
UNAVAILABLE_GLOBALS = frozenset({"apply", "as_function", "lipsum", "pack", "unpack"})
BLOCKED_TEXT_METHODS = frozenset({"expandtabs", "format", "format_map", "translate"})

# Limits used by the dashboard converter.
MAX_CHARTS_PER_PAGE = 4
MAX_ARCS_PER_PAGE = 4
MAX_H_GRADIENTS_PER_PAGE = 4
MAX_PAGES = 20
MAX_NAV = 8

THEME_IDS = ("midnight", "daylight", "warm", "soft", "mono", "glass")
DEFAULT_THEME = "midnight"

# Regex sources; each is compiled where it is used.
ICON_RE = r"^mdi:[a-z0-9-]+$"
ID_RE = r"^[a-z0-9]+(-[a-z0-9]+)*/[a-z0-9]+(-[a-z0-9]+)*$"
VERSION_RE = r"^\d+\.\d+\.\d+$"
SIZE_RE = r"^[1-6]x[1-4]$"
NAME_RE = r"^[a-z][a-z0-9_]{0,31}$"
DOMAIN_RE = r"^[a-z][a-z0-9_]*$"
DATA_KEY_RE = r"^[a-z][a-z0-9_]*$"
VAR_RE = r"^\{\{\s*([a-z][a-z0-9_]*)\s*\}\}$"
DURATION_RE = r"^(\d+)(s|min|h)$"
ACTION_RE = r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$"
COLOR_RE = r"^#[0-9A-Fa-f]{6}$"
ENTITY_ID_RE = r"^[a-z0-9_]+\.[a-z0-9_]+$"
PAGE_PATH_RE = r"^[a-z0-9_-]{1,64}$"

DURATION_UNITS = {"s": 1, "min": 60, "h": 3600}

FEEDBACK_MODES = ("optimistic", "pulse", "progress", "confirm")
LOCAL_ACTIONS = ("open_details", "open_live", "go_to_page")

ALLOWED_ACTION_DOMAINS = frozenset(
    {
        "alarm_control_panel",
        "button",
        "climate",
        "cover",
        "fan",
        "humidifier",
        "input_boolean",
        "input_button",
        "input_number",
        "input_select",
        "light",
        "lock",
        "media_player",
        "number",
        "scene",
        "script",
        "select",
        "siren",
        "switch",
        "vacuum",
        "valve",
        "water_heater",
    }
)
# Every script is also registered as its own service, script.<object_id>, which
# would run that script whatever entity the card picked. Script outputs may
# therefore use only the generic services that act on the given entity_id.
ALLOWED_DOMAIN_SERVICES = {"script": frozenset({"turn_on", "turn_off", "toggle"})}
SENSITIVE_DOMAINS = frozenset({"lock", "alarm_control_panel"})
CONFIRM_COVER_CLASSES = frozenset({"garage", "gate", "door"})
READ_ACTIONS = frozenset({"weather.get_forecasts"})

# Service data keys that would widen a call beyond the picked entity.
TARGET_KEYS = frozenset({"area_id", "device_id", "floor_id", "label_id", "target"})

RESERVED_NAMES = frozenset({"value", "response", "component_name"})
RESERVED_NAMESPACES = frozenset({"apollo"})
