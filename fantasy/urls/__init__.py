from django.urls import path, include
from .core import urlpatterns as core_urlpatterns
from .modules.swiss import urlpatterns as swiss_urlpatterns

app_name = "fantasy"

urlpatterns = [
    # Core URLs (home, auth, tournaments, profiles)
    path("", include((core_urlpatterns, "fantasy_core"))),
    # Swiss module URLs
    path("swiss/", include((swiss_urlpatterns, "fantasy_swiss"))),
]

__all__ = ["urlpatterns"]
