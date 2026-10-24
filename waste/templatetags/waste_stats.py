from django import template

from waste.services import user_impact

register = template.Library()


@register.simple_tag
def waste_impact(user):
    return user_impact(user)
