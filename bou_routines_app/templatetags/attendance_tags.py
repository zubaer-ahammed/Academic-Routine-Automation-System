from django import template

register = template.Library()

@register.filter
def dict_key(dictionary, key):
    """Get value from dictionary by key"""
    if dictionary and key in dictionary:
        return dictionary[key]
    return None
