import jwt
from channels.middleware import BaseMiddleware
from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.auth import get_user_model
from urllib.parse import parse_qs


@sync_to_async
def get_user_from_token(token: str):
    try:
        User = get_user_model()
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        user = User.objects.get(id=payload["user_id"])
        print(f"JWT decoded, user={user}")
        return user
    except Exception as e:
        print(f"Invalid token: {e}")
        return None


class JWTAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        from django.contrib.auth.models import AnonymousUser
        query_string = parse_qs(scope["query_string"].decode())
        token = query_string.get("token")

        scope["user"] = AnonymousUser()

        if token:
            user = await get_user_from_token(token[0])
            if user:
                scope["user"] = user
                print(f"🔑 Token OK → user set: {user}")
            else:
                print("❌ Token provided but no valid user found")
        else:
            print("❌ No token in query_string")

        return await super().__call__(scope, receive, send)
