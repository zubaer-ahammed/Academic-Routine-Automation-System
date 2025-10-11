from django import template

register = template.Library()

@register.filter
def dict_key(dictionary, key):
    """Get a value from a dictionary using a key"""
    if dictionary and isinstance(dictionary, dict):
        return dictionary.get(key)
    return None
