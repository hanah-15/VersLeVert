from functools import wraps

from django.core.exceptions import PermissionDenied
from django.contrib.auth.mixins import AccessMixin


def sponsor_required(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        if not request.user.is_sponsor:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapped


class SponsorRequiredMixin(AccessMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not request.user.is_sponsor:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class AdminRequiredMixin(AccessMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not request.user.is_staff:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


def owner_required(obj, user, owner_attr="sponsor"):
    owner = getattr(obj, owner_attr)
    account = getattr(user, "sponsor_account", None)
    if owner != user and owner != account:
        raise PermissionDenied
    return obj
