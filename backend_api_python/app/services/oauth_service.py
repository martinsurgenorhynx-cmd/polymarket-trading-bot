"""
OAuth Service - Handles Google and GitHub OAuth authentication.
"""
import os
import secrets
import requests
from urllib.parse import urlencode
from datetime import datetime
from typing import Tuple, Optional, Dict, Any
from app.utils.db import get_db_connection
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Singleton instance
_oauth_service = None


def get_oauth_service():
    """Get singleton OAuthService instance"""
    global _oauth_service
    if _oauth_service is None:
        _oauth_service = OAuthService()
    return _oauth_service


class OAuthService:
    """OAuth service for Google and GitHub authentication"""
    
    def __init__(self):
        self._load_config()
    
    def _load_config(self):
        """Load OAuth configuration from environment variables"""
        # Google OAuth
        self.google_client_id = os.getenv('GOOGLE_CLIENT_ID', '')
        self.google_client_secret = os.getenv('GOOGLE_CLIENT_SECRET', '')
        self.google_redirect_uri = os.getenv('GOOGLE_REDIRECT_URI', '')
        self.google_enabled = bool(self.google_client_id and self.google_client_secret)
        
        # GitHub OAuth
        self.github_client_id = os.getenv('GITHUB_CLIENT_ID', '')
        self.github_client_secret = os.getenv('GITHUB_CLIENT_SECRET', '')
        self.github_redirect_uri = os.getenv('GITHUB_REDIRECT_URI', '')
        self.github_enabled = bool(self.github_client_id and self.github_client_secret)
        
        # Frontend URL for redirect after OAuth
        self.frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:8080')
        
        # State storage (in-memory for simplicity, could use Redis in production)
        self._states = {}
    
    # =========================================================================
    # Google OAuth
    # =========================================================================
    
    def get_google_auth_url(self, state: str = None) -> Tuple[str, str]:
        """
        Generate Google OAuth authorization URL.
        
        Returns:
            (auth_url, state)
        """
        if not self.google_enabled:
            return '', ''
        
        state = state or secrets.token_urlsafe(32)
        self._states[state] = {'provider': 'google', 'created_at': datetime.now()}
        
        params = {
            'client_id': self.google_client_id,
            'redirect_uri': self.google_redirect_uri,
            'response_type': 'code',
            'scope': 'openid email profile',
            'state': state,
            'access_type': 'offline',
            'prompt': 'select_account'
        }
        
        auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
        return auth_url, state
    
    def handle_google_callback(self, code: str, state: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Handle Google OAuth callback.
        
        Args:
            code: Authorization code from Google
            state: State parameter for CSRF protection
        
        Returns:
            (success, user_info_or_error)
        """
        # Validate state
        if state not in self._states or self._states[state].get('provider') != 'google':
            return False, {'error': 'Invalid state parameter'}
        
        del self._states[state]
        
        try:
            # Exchange code for tokens
            token_response = requests.post(
                'https://oauth2.googleapis.com/token',
                data={
                    'code': code,
                    'client_id': self.google_client_id,
                    'client_secret': self.google_client_secret,
                    'redirect_uri': self.google_redirect_uri,
                    'grant_type': 'authorization_code'
                },
                timeout=10
            )
            
            if token_response.status_code != 200:
                logger.error(f"Google token exchange failed: {token_response.text}")
                return False, {'error': 'Failed to exchange authorization code'}
            
            tokens = token_response.json()
            access_token = tokens.get('access_token')
            
            # Get user info
            user_response = requests.get(
                'https://www.googleapis.com/oauth2/v2/userinfo',
                headers={'Authorization': f'Bearer {access_token}'},
                timeout=10
            )
            
            if user_response.status_code != 200:
                logger.error(f"Google user info failed: {user_response.text}")
                return False, {'error': 'Failed to get user information'}
            
            user_info = user_response.json()
            
            return True, {
                'provider': 'google',
                'provider_user_id': user_info.get('id'),
                'email': user_info.get('email'),
                'name': user_info.get('name'),
                'avatar': user_info.get('picture'),
                'access_token': access_token,
                'refresh_token': tokens.get('refresh_token')
            }
            
        except requests.RequestException as e:
            logger.error(f"Google OAuth error: {e}")
            return False, {'error': 'OAuth service unavailable'}
    
    # =========================================================================
    # GitHub OAuth
    # =========================================================================
    
    def get_github_auth_url(self, state: str = None) -> Tuple[str, str]:
        """
        Generate GitHub OAuth authorization URL.
        
        Returns:
            (auth_url, state)
        """
        if not self.github_enabled:
            return '', ''
        
        state = state or secrets.token_urlsafe(32)
        self._states[state] = {'provider': 'github', 'created_at': datetime.now()}
        
        params = {
            'client_id': self.github_client_id,
            'redirect_uri': self.github_redirect_uri,
            'scope': 'user:email read:user',
            'state': state
        }
        
        auth_url = f"https://github.com/login/oauth/authorize?{urlencode(params)}"
        return auth_url, state
    
    def handle_github_callback(self, code: str, state: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Handle GitHub OAuth callback.
        
        Args:
            code: Authorization code from GitHub
            state: State parameter for CSRF protection
        
        Returns:
            (success, user_info_or_error)
        """
        # Validate state
        if state not in self._states or self._states[state].get('provider') != 'github':
            return False, {'error': 'Invalid state parameter'}
        
        del self._states[state]
        
        try:
            # Exchange code for token
            token_response = requests.post(
                'https://github.com/login/oauth/access_token',
                data={
                    'client_id': self.github_client_id,
                    'client_secret': self.github_client_secret,
                    'code': code,
                    'redirect_uri': self.github_redirect_uri
                },
                headers={'Accept': 'application/json'},
                timeout=10
            )
            
            if token_response.status_code != 200:
                logger.error(f"GitHub token exchange failed: {token_response.text}")
                return False, {'error': 'Failed to exchange authorization code'}
            
            tokens = token_response.json()
            access_token = tokens.get('access_token')
            
            if not access_token:
                error = tokens.get('error_description', 'Unknown error')
                logger.error(f"GitHub token error: {error}")
                return False, {'error': error}
            
            # Get user info
            user_response = requests.get(
                'https://api.github.com/user',
                headers={
                    'Authorization': f'Bearer {access_token}',
                    'Accept': 'application/vnd.github.v3+json'
                },
                timeout=10
            )
            
            if user_response.status_code != 200:
                logger.error(f"GitHub user info failed: {user_response.text}")
                return False, {'error': 'Failed to get user information'}
            
            user_info = user_response.json()
            
            # Get user email (might be private)
            email = user_info.get('email')
            if not email:
                email_response = requests.get(
                    'https://api.github.com/user/emails',
                    headers={
                        'Authorization': f'Bearer {access_token}',
                        'Accept': 'application/vnd.github.v3+json'
                    },
                    timeout=10
                )
                if email_response.status_code == 200:
                    emails = email_response.json()
                    # Find primary email
                    for e in emails:
                        if e.get('primary') and e.get('verified'):
                            email = e.get('email')
                            break
                    # Fallback to any verified email
                    if not email:
                        for e in emails:
                            if e.get('verified'):
                                email = e.get('email')
                                break
            
            return True, {
                'provider': 'github',
                'provider_user_id': str(user_info.get('id')),
                'email': email,
                'name': user_info.get('name') or user_info.get('login'),
                'avatar': user_info.get('avatar_url'),
                'access_token': access_token,
                'refresh_token': None  # GitHub doesn't use refresh tokens
            }
            
        except requests.RequestException as e:
            logger.error(f"GitHub OAuth error: {e}")
            return False, {'error': 'OAuth service unavailable'}
    
    # =========================================================================
    # OAuth Link Management
    # =========================================================================
    
    def get_or_create_user_from_oauth(self, oauth_info: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        Get existing user or create new user from OAuth info.
        
        Args:
            oauth_info: Dict with provider, provider_user_id, email, name, avatar, tokens
        
        Returns:
            (success, user_or_error)
        """
        provider = oauth_info['provider']
        provider_user_id = oauth_info['provider_user_id']
        email = oauth_info.get('email')
        name = oauth_info.get('name', '')
        avatar = oauth_info.get('avatar', '/avatar2.jpg')
        
        try:
            with get_db_connection() as db:
                cur = db.cursor()
                
                # Check if OAuth link exists
                cur.execute(
                    """
                    SELECT user_id FROM qd_oauth_links
                    WHERE provider = ? AND provider_user_id = ?
                    """,
                    (provider, provider_user_id)
                )
                link = cur.fetchone()
                
                if link:
                    # Existing OAuth link - get user
                    user_id = link['user_id']
                    cur.execute(
                        """
                        SELECT id, username, email, nickname, avatar, status, role
                        FROM qd_users WHERE id = ?
                        """,
                        (user_id,)
                    )
                    user = cur.fetchone()
                    
                    if user:
                        # Update OAuth tokens
                        cur.execute(
                            """
                            UPDATE qd_oauth_links 
                            SET access_token = ?, refresh_token = ?, updated_at = NOW()
                            WHERE provider = ? AND provider_user_id = ?
                            """,
                            (oauth_info.get('access_token'), oauth_info.get('refresh_token'),
                             provider, provider_user_id)
                        )
                        
                        # Update last login
                        cur.execute(
                            "UPDATE qd_users SET last_login_at = NOW() WHERE id = ?",
                            (user_id,)
                        )
                        db.commit()
                        cur.close()
                        return True, dict(user)
                    else:
                        # Orphaned OAuth link - remove it
                        cur.execute(
                            "DELETE FROM qd_oauth_links WHERE provider = ? AND provider_user_id = ?",
                            (provider, provider_user_id)
                        )
                        db.commit()
                
                # Check if user exists with same email
                if email:
                    cur.execute(
                        """
                        SELECT id, username, email, nickname, avatar, status, role
                        FROM qd_users WHERE email = ?
                        """,
                        (email,)
                    )
                    existing_user = cur.fetchone()
                    
                    if existing_user:
                        # Link OAuth to existing user
                        cur.execute(
                            """
                            INSERT INTO qd_oauth_links 
                            (user_id, provider, provider_user_id, provider_email, 
                             provider_name, provider_avatar, access_token, refresh_token)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (existing_user['id'], provider, provider_user_id, email,
                             name, avatar, oauth_info.get('access_token'), 
                             oauth_info.get('refresh_token'))
                        )
                        cur.execute(
                            "UPDATE qd_users SET last_login_at = NOW() WHERE id = ?",
                            (existing_user['id'],)
                        )
                        db.commit()
                        cur.close()
                        return True, dict(existing_user)
                
                # Create new user
                # Generate unique username from OAuth name or email
                base_username = (name or email.split('@')[0] if email else provider_user_id)
                base_username = ''.join(c for c in base_username if c.isalnum() or c in '_-')[:30]
                username = base_username
                
                # Ensure username is unique
                counter = 1
                while True:
                    cur.execute("SELECT id FROM qd_users WHERE username = ?", (username,))
                    if not cur.fetchone():
                        break
                    username = f"{base_username}_{counter}"
                    counter += 1
                
                # Generate a random password (user won't need it for OAuth login)
                import secrets
                random_password = secrets.token_urlsafe(32)
                from app.services.user_service import get_user_service
                password_hash = get_user_service().hash_password(random_password)
                
                # Ensure email is unique or generate placeholder
                if email:
                    cur.execute("SELECT id FROM qd_users WHERE email = ?", (email,))
                    if cur.fetchone():
                        email = f"{provider}_{provider_user_id}@oauth.local"
                else:
                    email = f"{provider}_{provider_user_id}@oauth.local"
                
                # Insert new user
                cur.execute(
                    """
                    INSERT INTO qd_users 
                    (username, password_hash, email, nickname, avatar, status, role, email_verified)
                    VALUES (?, ?, ?, ?, ?, 'active', 'user', TRUE)
                    """,
                    (username, password_hash, email, name or username, avatar or '/avatar2.jpg')
                )
                user_id = cur.lastrowid
                
                # Create OAuth link
                cur.execute(
                    """
                    INSERT INTO qd_oauth_links 
                    (user_id, provider, provider_user_id, provider_email, 
                     provider_name, provider_avatar, access_token, refresh_token)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (user_id, provider, provider_user_id, oauth_info.get('email'),
                     name, avatar, oauth_info.get('access_token'), 
                     oauth_info.get('refresh_token'))
                )
                
                # Update last_login_at for new OAuth users
                cur.execute(
                    "UPDATE qd_users SET last_login_at = NOW() WHERE id = ?",
                    (user_id,)
                )
                
                db.commit()
                cur.close()

                # Grant registration bonus credits for OAuth-created users
                # Keep consistent with email/password registration flows (auth.py).
                try:
                    register_bonus = int(os.getenv('CREDITS_REGISTER_BONUS', '0'))
                except (ValueError, TypeError):
                    register_bonus = 0
                if register_bonus > 0:
                    try:
                        from app.services.billing_service import get_billing_service
                        get_billing_service().add_credits(
                            user_id=user_id,
                            amount=register_bonus,
                            action='register_bonus',
                            remark=f'Registration bonus (OAuth:{provider})'
                        )
                    except Exception as e:
                        logger.warning(f"Failed to grant OAuth registration bonus: {e}")
                
                return True, {
                    'id': user_id,
                    'username': username,
                    'email': email,
                    'nickname': name or username,
                    'avatar': avatar or '/avatar2.jpg',
                    'status': 'active',
                    'role': 'user'
                }
                
        except Exception as e:
            logger.error(f"OAuth user creation failed: {e}")
            return False, {'error': 'Failed to create user account'}
    
    def get_user_oauth_links(self, user_id: int) -> list:
        """Get all OAuth links for a user"""
        try:
            with get_db_connection() as db:
                cur = db.cursor()
                cur.execute(
                    """
                    SELECT provider, provider_email, provider_name, created_at
                    FROM qd_oauth_links WHERE user_id = ?
                    """,
                    (user_id,)
                )
                links = cur.fetchall()
                cur.close()
                return [dict(link) for link in links] if links else []
        except Exception as e:
            logger.error(f"Failed to get OAuth links: {e}")
            return []
    
    def unlink_oauth(self, user_id: int, provider: str) -> Tuple[bool, str]:
        """Unlink an OAuth provider from user account"""
        try:
            with get_db_connection() as db:
                cur = db.cursor()
                
                # Check if user has password (can't unlink last auth method)
                cur.execute(
                    "SELECT password_hash FROM qd_users WHERE id = ?",
                    (user_id,)
                )
                user = cur.fetchone()
                
                if not user or not user['password_hash']:
                    # Check if this is the only OAuth link
                    cur.execute(
                        "SELECT COUNT(*) as count FROM qd_oauth_links WHERE user_id = ?",
                        (user_id,)
                    )
                    count = cur.fetchone()['count']
                    if count <= 1:
                        cur.close()
                        return False, 'Cannot unlink the only authentication method'
                
                cur.execute(
                    "DELETE FROM qd_oauth_links WHERE user_id = ? AND provider = ?",
                    (user_id, provider)
                )
                db.commit()
                cur.close()
                return True, 'unlinked'
                
        except Exception as e:
            logger.error(f"Failed to unlink OAuth: {e}")
            return False, 'Failed to unlink account'
    
    # =========================================================================
    # Cleanup
    # =========================================================================
    
    def cleanup_expired_states(self, max_age_minutes: int = 10):
        """Clean up expired OAuth states"""
        cutoff = datetime.now()
        from datetime import timedelta
        cutoff = cutoff - timedelta(minutes=max_age_minutes)
        
        expired = [k for k, v in self._states.items() 
                   if v.get('created_at', datetime.now()) < cutoff]
        for k in expired:
            del self._states[k]
