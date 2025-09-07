import jwt
from channels.middleware import BaseMiddleware
from channels.db import database_sync_to_async
from django.conf import settings
from django.contrib.auth import get_user_model
from urllib.parse import parse_qs


@database_sync_to_async
def get_user_from_token(token):
    try:

        User = get_user_model()
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        user = User.objects.get(id=payload["user_id"])
        return user
    except Exception:
        return None


class JWTAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        query_string = parse_qs(scope["query_string"].decode())
        token = query_string.get("token")

        if token:
            user = await get_user_from_token(token[0])
            if user:
                scope["user"] = user

        return await super().__call__(scope, receive, send)
