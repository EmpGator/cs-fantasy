from dataclasses import asdict, is_dataclass
from django import template
from django.template.loader import get_template

register = template.Library()


@register.simple_tag(takes_context=True)
def dynamic_include(context, template_name, keys_dict):
    """
    Renders the given template.
    It takes a dictionary (keys_dict) and "unpacks" its contents
    directly into the context for the included template.
    """

    template_instance = get_template(template_name)

    if isinstance(keys_dict, dict):
        return template_instance.render(keys_dict)
    return None


@register.filter
def get_item(dictionary, key):
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None


@register.filter
def dataclass_asdict(value):
    """
    Convert dataclass instances to serializable dicts for use with json_script.
    Does NOT perform JSON encoding - that's handled by json_script.

    This allows passing dataclass instances to templates while still being
    able to serialize them for JavaScript consumption via json_script.

    Usage:
        {{ my_dataclass|dataclass_asdict|json_script:"my-data-id" }}
        {{ my_dataclass_list|dataclass_asdict|json_script:"my-list-id" }}
    """
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    elif isinstance(value, list):
        return [
            asdict(item) if is_dataclass(item) and not isinstance(item, type) else item
            for item in value
        ]
    elif isinstance(value, dict):
        # Handle dicts that might contain dataclass instances
        return {
            k: asdict(v) if is_dataclass(v) and not isinstance(v, type) else v
            for k, v in value.items()
        }

    # Return value as-is if it's not a dataclass
    return value
