from django.contrib.auth.backends import BaseBackend
from fantasy.models import User


class SlugOrEmailBackend(BaseBackend):
    """
    Custom authentication backend that supports login with either slug or email.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or not password:
            return None

        user = None
        try:
            user = User.objects.get(email=username)
        except User.DoesNotExist:
            try:
                user = User.objects.get(slug=username)
            except User.DoesNotExist:
                return None

        if user.check_password(password):
            if user.uses_password or user.is_superuser:
                return user

        return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
