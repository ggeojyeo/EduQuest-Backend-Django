import jwt
import requests
import pytz
from datetime import datetime
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import AuthenticationFailed
from django.conf import settings
from .models import EduquestUser
from .utils import split_full_name


class CustomJWTAuthentication(JWTAuthentication):

    def authenticate(self, request):
        header = self.get_header(request)
        if header is None:
            return self.session_authenticate(request)

        raw_token = self.get_raw_token(header)
        if raw_token is None:
            return self.session_authenticate(request)

        try:
            validated_token = self.get_validated_token(raw_token)
            if validated_token.get('user_id'):
                user = self.get_user(validated_token)
            else:
                user = self.get_or_create_user(validated_token)
            return user, validated_token
        except AuthenticationFailed as e:
            print(f"Authentication failed: {str(e)}")
            raise e
        except Exception as e:
            print(f"Unexpected error: {str(e)}")
            raise AuthenticationFailed(f"Unexpected error: {str(e)}")

    def get_validated_token(self, raw_token):
        try:
            return super().get_validated_token(raw_token)
        except AuthenticationFailed:
            pass
        except Exception:
            pass

        try:
            # Decode the token without verification to get the payload
            unverified_header = jwt.get_unverified_header(raw_token)
            unverified_payload = jwt.decode(raw_token, options={"verify_signature": False})

            issuer = unverified_payload.get('iss')
            tenant_id = unverified_payload.get('tid') or getattr(settings, 'AZURE_TENANT_ID', None)

            # Resolve JWKS URL. Prefer the issuer's OpenID configuration when available.
            jwks_url = None
            if issuer:
                # Discover jwks_uri from the issuer's configuration
                openid_cfg_url = issuer.rstrip('/') + '/.well-known/openid-configuration'
                cfg_resp = requests.get(openid_cfg_url, timeout=5)
                if cfg_resp.status_code == 200:
                    jwks_url = cfg_resp.json().get('jwks_uri')
            # Fallback to tenant-based endpoint if discovery failed
            if not jwks_url and tenant_id:
                jwks_url = f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"

            if not jwks_url:
                raise AuthenticationFailed('Could not determine JWKS endpoint for token verification.')

            response = requests.get(jwks_url, timeout=5)
            response.raise_for_status()

            # The keys are used to verify the token signature
            keys = response.json().get('keys')
            key = None
            try:
                key = next(k for k in keys if k['kid'] == unverified_header['kid'])
            except StopIteration:
                raise AuthenticationFailed(f"No matching JWK found for kid={unverified_header.get('kid')} at {jwks_url}")
            public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key)

            # Validate the token using the public key. Accept both client-id and api://client-id audiences.
            expected_audiences = [
                settings.AZURE_CLIENT_ID,
                f"api://{settings.AZURE_CLIENT_ID}",
            ]
            decoded_token = jwt.decode(
                raw_token,
                key=public_key,
                algorithms=["RS256"],
                audience=expected_audiences,
            )
            return decoded_token
        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed('Token has expired, please authenticate again.')
        except jwt.InvalidAudienceError:
            raise AuthenticationFailed('Invalid audience.')
        except jwt.DecodeError:
            raise AuthenticationFailed('Error decoding token.')
        except jwt.PyJWTError as e:
            raise AuthenticationFailed(f'Token is invalid: {str(e)}')

    def get_or_create_user(self, validated_token):
        try:
            # Try multiple possible email claims
            email = validated_token.get('preferred_username') or validated_token.get('email') or validated_token.get('upn')
            
            if not email:
                raise AuthenticationFailed('No email found in token. Token claims: ' + str(validated_token.keys()))
            
            domain = email.split('@')[1]
            if domain == 'e.ntu.edu.sg':
                is_staff = False
            elif 'ntu.edu.sg' in domain or 'staff.main.edu.sg' in domain:
                is_staff = True
            else:
                raise AuthenticationFailed('Invalid domain.')
            username = validated_token.get('name', '')
            formatted_username = username.replace('#', '')
            first_name, last_name = split_full_name(formatted_username)
            last_login = datetime.fromtimestamp(validated_token.get('iat'))
            # Define SGT timezone
            sgt_timezone = pytz.timezone("Asia/Singapore")
            sgt_datetime = sgt_timezone.localize(datetime.strptime(str(last_login), "%Y-%m-%d %H:%M:%S"))
            # Convert to UTC
            utc_timezone = pytz.utc
            last_login = sgt_datetime.astimezone(utc_timezone)

            user, created = EduquestUser.objects.get_or_create(
                email=email.upper(),
                defaults={
                    'email': email.upper(),
                    'username': username,
                    'nickname': username,
                    'first_name': first_name,
                    'last_name': last_name,
                    'last_login': last_login,
                    'is_staff': is_staff
                }
            )
            if created:
                # Here you can add any additional setup for the new user
                pass
            else:
                user.last_login = last_login
                user.save()

            return user
        except Exception as e:
            raise AuthenticationFailed(f'Failed to get or create user: {str(e)}')

    def session_authenticate(self, request):
        session_authenticator = SessionAuthentication()
        try:
            return session_authenticator.authenticate(request)
        except AuthenticationFailed as e:
            return None
        except Exception as e:
            return None
