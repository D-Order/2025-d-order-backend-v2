import jwt
from channels.middleware import BaseMiddleware
from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.auth import get_user_model
from urllib.parse import parse_qs
import logging

logger = logging.getLogger(__name__)

@sync_to_async(thread_sensitive=True)
def get_user_from_token(token: str):
    try:
        User = get_user_model()
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        user = User.objects.get(id=payload["user_id"])
        logger.debug(f"[JWTAuthMiddleware] JWT decoded → user={user}")
        return user
    except Exception as e:
        logger.error(f"[JWTAuthMiddleware] Invalid token: {e}", exc_info=True)
        return None


class JWTAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        from django.contrib.auth.models import AnonymousUser
        logger.info(">>> Entering JWTAuthMiddleware.__call__")

        query_string = parse_qs(scope["query_string"].decode())
        token = query_string.get("token")

        scope["user"] = AnonymousUser()

        if token:
            user = await get_user_from_token(token[0])
            if user:
                scope["user"] = user
                logger.info(f"[JWTAuthMiddleware] Token OK → user set: {user}")
            else:
                logger.warning("[JWTAuthMiddleware] Token provided but no valid user found")
        else:
            logger.warning("[JWTAuthMiddleware] No token in query_string")

        return await super().__call__(scope, receive, send)
