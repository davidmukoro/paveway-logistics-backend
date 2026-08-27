# core/cookie_auth.py

from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed
from setup.models import UserSession  # adjust import


class CookieJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        raw_token = request.COOKIES.get("access_token")

        if raw_token is None:
            return None

        try:
            validated_token = self.get_validated_token(raw_token)
            user = self.get_user(validated_token)

            # 🔥 NEW: Validate session
            session_id = validated_token.get("session_id")

            if session_id:
                session = UserSession.objects.filter(
                    id=session_id, is_active=True
                ).first()

                if not session:
                    raise AuthenticationFailed("Session expired or logged out")

                # (Optional) attach session to request
                request.user_session = session

            return (user, validated_token)

        except AuthenticationFailed:
            raise
        except Exception:
            raise AuthenticationFailed("Invalid or expired token")
