from django import template

register = template.Library()

@register.simple_tag(takes_context=True)
def has_feature(context, feature_key):
    request = context.get('request')
    if request and hasattr(request, 'user'):
        # Platform Admins don't have tenant feature locks inside the main app
        if getattr(request.user, 'role', '') == 'Platform Admin':
            return True
        return feature_key in getattr(request.user, 'features', [])
    return False
