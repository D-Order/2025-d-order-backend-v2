import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")
django.setup()

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from channels.auth import AuthMiddlewareStack
from project.middleware import JWTAuthMiddleware
import project.routing

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": JWTAuthMiddleware(   # JWT 인증 적용
        AuthMiddlewareStack(
            URLRouter(project.routing.websocket_urlpatterns)
        )
    ),
})
