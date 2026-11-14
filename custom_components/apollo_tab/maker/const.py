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

# Card files of schema 2 (C.2 of the cards spec). Schema 1 keeps the limits
# above; these are the limits of one schema 2 file.
MAX_PARAMS_2 = 8
MAX_OPTIONS_2 = 16
MAX_INPUTS_2 = 32
MAX_OUTPUTS_2 = 16
MAX_PARTS_2 = 32
MAX_VARIANTS_2 = 6
MAX_VARIANT_ITEMS_2 = 24
MAX_WIDGETS_2 = 48
MAX_LOOP_COPIES_2 = 16
MAX_ROW_ITEMS_2 = 8
MAX_WHEN_TERMS = 6
MAX_NOTES_2 = 4
MAX_REPLACES_2 = 8
MAX_MULTIPLE_2 = 16
MAX_CHOICES_2 = 8
MAX_COLOURS_2 = 8
MAX_TEXT_OPTION_2 = 40
MAX_LABEL_2 = 40
MAX_HELP_2 = 120
MAX_CHOICE_OPTIONS_2 = 16
MAX_TRACK_2 = 8
MAX_FACT_LIST_2 = 64

# Names a schema 2 file may not give to a param, option, input, output,
# loop or vars entry. The standard options live in a card's options too.
RESERVED_NAMES_2 = frozenset(
    {"can", "has", "tablet", "option", "value", "response", "component_name"}
)
STANDARD_OPTIONS_2 = frozenset({"icon", "tap", "tap_page", "hold", "ask"})
CARD_GROUPS = (
    "lights",
    "climate",
    "covers",
    "security",
    "media",
    "sensors",
    "home",
    "more",
)
HEADER_FORMS = ("title", "chip", "tile", "tile_v", "none")
OPTION_SECTIONS = ("shows", "controls", "look")
OPTION_TYPES = ("toggle", "choice", "number", "text", "icon", "colour", "colours")
COLOUR_ROLES = ("accent", "accent2", "good", "warn", "bad", "info", "text", "muted")
LABEL_SIZES_2 = ("s", "m", "ml", "l", "xl", "xxl", "huge")
LIT_LOOKS = ("fill", "icon", "outline", "none")
LOCAL_ACTIONS_2 = ("open_details", "open_live", "go_to_page", "detail", "back")
USES_TYPES = ("number", "bool", "entities")
# Data keys that may hold a list of numbers in a schema 2 output.
COLOUR_DATA_KEYS = frozenset(
    {"hs_color", "rgb_color", "rgbw_color", "rgbww_color", "xy_color"}
)
# A white of a given warmth in a colours option, as "2700K".
KELVIN_RE = r"^([0-9]{4,5})K$"
KELVIN_RANGE = (1500, 10000)
# '{{ name }}' or '{{ name.key }}', the reference forms of C.2.7.
REF_RE = r"^\{\{\s*([a-z][a-z0-9_]*)(?:\.([a-z][a-z0-9_]*))?\s*\}\}$"
CHOICE_KEY_RE = r"^[a-z0-9][a-z0-9_]{0,31}$"
WHEN_VALUE_RE = r"^[a-z0-9_]+$"

# Allowed services per domain (C.2.8). Every service takes the entity_id of a
# device the card was set up with; services whose data names other entities,
# or a free address or command, are left out.
ALLOWED_SERVICES = {
    "alarm_control_panel": frozenset(
        {
            "alarm_arm_home",
            "alarm_arm_away",
            "alarm_arm_night",
            "alarm_arm_vacation",
            "alarm_arm_custom_bypass",
            "alarm_disarm",
        }
    ),
    "button": frozenset({"press"}),
    "input_button": frozenset({"press"}),
    "climate": frozenset(
        {
            "set_temperature",
            "set_hvac_mode",
            "set_preset_mode",
            "set_fan_mode",
            "set_swing_mode",
            "set_humidity",
            "turn_on",
            "turn_off",
            "toggle",
        }
    ),
    "cover": frozenset(
        {
            "open_cover",
            "close_cover",
            "stop_cover",
            "toggle",
            "set_cover_position",
            "open_cover_tilt",
            "close_cover_tilt",
            "stop_cover_tilt",
            "set_cover_tilt_position",
        }
    ),
    "fan": frozenset(
        {
            "turn_on",
            "turn_off",
            "toggle",
            "set_percentage",
            "set_preset_mode",
            "oscillate",
            "set_direction",
        }
    ),
    "humidifier": frozenset(
        {"turn_on", "turn_off", "toggle", "set_humidity", "set_mode"}
    ),
    "input_boolean": frozenset({"turn_on", "turn_off", "toggle"}),
    "switch": frozenset({"turn_on", "turn_off", "toggle"}),
    "siren": frozenset({"turn_on", "turn_off", "toggle"}),
    "input_number": frozenset({"set_value"}),
    "number": frozenset({"set_value"}),
    "input_select": frozenset({"select_option", "select_next", "select_previous"}),
    "select": frozenset({"select_option", "select_next", "select_previous"}),
    "light": frozenset({"turn_on", "turn_off", "toggle"}),
    "lock": frozenset({"lock", "unlock", "open"}),
    "media_player": frozenset(
        {
            "turn_on",
            "turn_off",
            "toggle",
            "media_play",
            "media_pause",
            "media_play_pause",
            "media_stop",
            "media_next_track",
            "media_previous_track",
            "volume_set",
            "volume_mute",
            "media_seek",
            "select_source",
            "shuffle_set",
            "repeat_set",
        }
    ),
    "scene": frozenset({"turn_on"}),
    "script": frozenset({"turn_on", "turn_off", "toggle"}),
    "vacuum": frozenset(
        {"start", "pause", "stop", "return_to_base", "locate", "set_fan_speed"}
    ),
    "valve": frozenset(
        {"open_valve", "close_valve", "stop_valve", "toggle", "set_valve_position"}
    ),
    "water_heater": frozenset(
        {"set_temperature", "set_operation_mode", "turn_on", "turn_off"}
    ),
}
