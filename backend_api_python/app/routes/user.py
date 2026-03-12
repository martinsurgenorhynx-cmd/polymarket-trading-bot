"""
User Management API Routes

Provides endpoints for user CRUD operations, role management, etc.
Only accessible by admin users.
"""
import json
from flask import Blueprint, request, jsonify, g
from app.services.user_service import get_user_service
from app.utils.auth import login_required, admin_required
from app.utils.db import get_db_connection
from app.utils.logger import get_logger

logger = get_logger(__name__)

user_bp = Blueprint('user_manage', __name__)


@user_bp.route('/list', methods=['GET'])
@login_required
@admin_required
def list_users():
    """
    List all users (admin only).
    
    Query params:
        page: int (default 1)
        page_size: int (default 20, max 100)
        search: str (optional, search by username/email/nickname)
    """
    try:
        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('page_size', 20, type=int)
        search = request.args.get('search', '', type=str)
        page_size = min(100, max(1, page_size))
        
        result = get_user_service().list_users(page=page, page_size=page_size, search=search)
        
        return jsonify({
            'code': 1,
            'msg': 'success',
            'data': result
        })
    except Exception as e:
        logger.error(f"list_users failed: {e}")
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


@user_bp.route('/detail', methods=['GET'])
@login_required
@admin_required
def get_user_detail():
    """Get user detail by ID (admin only)"""
    try:
        user_id = request.args.get('id', type=int)
        if not user_id:
            return jsonify({'code': 0, 'msg': 'Missing user id', 'data': None}), 400
        
        user = get_user_service().get_user_by_id(user_id)
        if not user:
            return jsonify({'code': 0, 'msg': 'User not found', 'data': None}), 404
        
        return jsonify({
            'code': 1,
            'msg': 'success',
            'data': user
        })
    except Exception as e:
        logger.error(f"get_user_detail failed: {e}")
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


@user_bp.route('/create', methods=['POST'])
@login_required
@admin_required
def create_user():
    """
    Create a new user (admin only).
    
    Request body:
        username: str (required)
        password: str (required)
        email: str (optional)
        nickname: str (optional)
        role: str (optional, default 'user')
    """
    try:
        data = request.get_json() or {}
        
        user_id = get_user_service().create_user(data)
        
        return jsonify({
            'code': 1,
            'msg': 'User created successfully',
            'data': {'id': user_id}
        })
    except ValueError as e:
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 400
    except Exception as e:
        logger.error(f"create_user failed: {e}")
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


@user_bp.route('/update', methods=['PUT'])
@login_required
@admin_required
def update_user():
    """
    Update user information (admin only).
    
    Query params:
        id: int (required)
    
    Request body:
        email: str (optional)
        nickname: str (optional)
        role: str (optional)
        status: str (optional)
    """
    try:
        user_id = request.args.get('id', type=int)
        if not user_id:
            return jsonify({'code': 0, 'msg': 'Missing user id', 'data': None}), 400
        
        data = request.get_json() or {}
        
        success = get_user_service().update_user(user_id, data)
        
        if success:
            return jsonify({'code': 1, 'msg': 'User updated successfully', 'data': None})
        else:
            return jsonify({'code': 0, 'msg': 'Update failed', 'data': None}), 400
    except Exception as e:
        logger.error(f"update_user failed: {e}")
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


@user_bp.route('/delete', methods=['DELETE'])
@login_required
@admin_required
def delete_user():
    """Delete a user (admin only)"""
    try:
        user_id = request.args.get('id', type=int)
        if not user_id:
            return jsonify({'code': 0, 'msg': 'Missing user id', 'data': None}), 400
        
        # Prevent deleting self
        if hasattr(g, 'user_id') and g.user_id == user_id:
            return jsonify({'code': 0, 'msg': 'Cannot delete yourself', 'data': None}), 400
        
        success = get_user_service().delete_user(user_id)
        
        if success:
            return jsonify({'code': 1, 'msg': 'User deleted successfully', 'data': None})
        else:
            return jsonify({'code': 0, 'msg': 'Delete failed', 'data': None}), 400
    except Exception as e:
        logger.error(f"delete_user failed: {e}")
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


@user_bp.route('/reset-password', methods=['POST'])
@login_required
@admin_required
def reset_user_password():
    """
    Reset a user's password (admin only).
    
    Request body:
        user_id: int (required)
        new_password: str (required)
    """
    try:
        data = request.get_json() or {}
        user_id = data.get('user_id')
        new_password = data.get('new_password', '')
        
        if not user_id:
            return jsonify({'code': 0, 'msg': 'Missing user_id', 'data': None}), 400
        
        if len(new_password) < 6:
            return jsonify({'code': 0, 'msg': 'Password must be at least 6 characters', 'data': None}), 400
        
        success = get_user_service().reset_password(user_id, new_password)
        
        if success:
            return jsonify({'code': 1, 'msg': 'Password reset successfully', 'data': None})
        else:
            return jsonify({'code': 0, 'msg': 'Reset failed', 'data': None}), 400
    except ValueError as e:
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 400
    except Exception as e:
        logger.error(f"reset_user_password failed: {e}")
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


@user_bp.route('/roles', methods=['GET'])
@login_required
@admin_required
def get_roles():
    """Get available roles and their permissions"""
    service = get_user_service()
    
    roles = []
    for role in service.ROLES:
        roles.append({
            'id': role,
            'name': role.capitalize(),
            'permissions': service.get_user_permissions(role)
        })
    
    return jsonify({
        'code': 1,
        'msg': 'success',
        'data': {'roles': roles}
    })


# ==================== Billing Management (Admin) ====================

@user_bp.route('/set-credits', methods=['POST'])
@login_required
@admin_required
def set_user_credits():
    """
    Set user credits (admin only).
    
    Request body:
        user_id: int (required)
        credits: int (required)
        remark: str (optional)
    """
    try:
        from app.services.billing_service import get_billing_service
        
        data = request.get_json() or {}
        user_id = data.get('user_id')
        credits = data.get('credits')
        remark = data.get('remark', '')
        
        if not user_id:
            return jsonify({'code': 0, 'msg': 'Missing user_id', 'data': None}), 400
        
        if credits is None or credits < 0:
            return jsonify({'code': 0, 'msg': 'Credits must be a non-negative number', 'data': None}), 400
        
        operator_id = getattr(g, 'user_id', None)
        success, result = get_billing_service().set_credits(user_id, int(credits), remark, operator_id)
        
        if success:
            return jsonify({'code': 1, 'msg': 'Credits updated successfully', 'data': {'credits': result}})
        else:
            return jsonify({'code': 0, 'msg': result, 'data': None}), 400
    except Exception as e:
        logger.error(f"set_user_credits failed: {e}")
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


@user_bp.route('/set-vip', methods=['POST'])
@login_required
@admin_required
def set_user_vip():
    """
    Set user VIP status (admin only).
    
    Request body:
        user_id: int (required)
        vip_days: int (optional, 0 to cancel VIP, positive number to grant VIP for days)
        vip_expires_at: str (optional, ISO format datetime, overrides vip_days if provided)
        remark: str (optional)
    """
    try:
        from datetime import datetime, timedelta, timezone
        from app.services.billing_service import get_billing_service
        
        data = request.get_json() or {}
        user_id = data.get('user_id')
        vip_days = data.get('vip_days')
        vip_expires_at_str = data.get('vip_expires_at')
        remark = data.get('remark', '')
        
        if not user_id:
            return jsonify({'code': 0, 'msg': 'Missing user_id', 'data': None}), 400
        
        # Calculate expires_at
        expires_at = None
        if vip_expires_at_str:
            try:
                expires_at = datetime.fromisoformat(vip_expires_at_str.replace('Z', '+00:00'))
            except ValueError:
                return jsonify({'code': 0, 'msg': 'Invalid vip_expires_at format', 'data': None}), 400
        elif vip_days is not None:
            if vip_days > 0:
                expires_at = datetime.now(timezone.utc) + timedelta(days=vip_days)
            else:
                expires_at = None  # Cancel VIP
        else:
            return jsonify({'code': 0, 'msg': 'Provide vip_days or vip_expires_at', 'data': None}), 400
        
        operator_id = getattr(g, 'user_id', None)
        success, result = get_billing_service().set_vip(user_id, expires_at, remark, operator_id)
        
        if success:
            return jsonify({
                'code': 1, 
                'msg': 'VIP status updated successfully', 
                'data': {'vip_expires_at': expires_at.isoformat() if expires_at else None}
            })
        else:
            return jsonify({'code': 0, 'msg': result, 'data': None}), 400
    except Exception as e:
        logger.error(f"set_user_vip failed: {e}")
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


@user_bp.route('/credits-log', methods=['GET'])
@login_required
@admin_required
def get_user_credits_log():
    """
    Get user credits log (admin only).
    
    Query params:
        user_id: int (required)
        page: int (default 1)
        page_size: int (default 20)
    """
    try:
        from app.services.billing_service import get_billing_service
        
        user_id = request.args.get('user_id', type=int)
        if not user_id:
            return jsonify({'code': 0, 'msg': 'Missing user_id', 'data': None}), 400
        
        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('page_size', 20, type=int)
        page_size = min(100, max(1, page_size))
        
        result = get_billing_service().get_credits_log(user_id, page, page_size)
        
        return jsonify({'code': 1, 'msg': 'success', 'data': result})
    except Exception as e:
        logger.error(f"get_user_credits_log failed: {e}")
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


# Self-service endpoints (accessible by any logged-in user)

@user_bp.route('/profile', methods=['GET'])
@login_required
def get_profile():
    """Get current user's profile with billing info and notification settings"""
    try:
        import json
        from app.services.billing_service import get_billing_service
        from app.utils.db import get_db_connection
        
        user_id = getattr(g, 'user_id', None)
        if not user_id:
            return jsonify({'code': 0, 'msg': 'Not authenticated', 'data': None}), 401
        
        user = get_user_service().get_user_by_id(user_id)
        if not user:
            return jsonify({'code': 0, 'msg': 'User not found', 'data': None}), 404
        
        # Add permissions
        user['permissions'] = get_user_service().get_user_permissions(user.get('role', 'user'))
        
        # Add billing info
        billing_info = get_billing_service().get_user_billing_info(user_id)
        user['billing'] = billing_info
        
        # Add notification settings
        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute("SELECT notification_settings FROM qd_users WHERE id = ?", (user_id,))
            row = cur.fetchone()
            cur.close()
        
        settings_str = (row.get('notification_settings') if row else '') or ''
        notification_settings = {}
        if settings_str:
            try:
                notification_settings = json.loads(settings_str)
            except Exception:
                notification_settings = {}
        
        # Default values
        if 'default_channels' not in notification_settings:
            notification_settings['default_channels'] = ['browser']
        
        user['notification_settings'] = notification_settings
        
        return jsonify({
            'code': 1,
            'msg': 'success',
            'data': user
        })
    except Exception as e:
        logger.error(f"get_profile failed: {e}")
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


@user_bp.route('/profile/update', methods=['PUT'])
@login_required
def update_profile():
    """
    Update current user's profile (limited fields).
    
    Request body:
        nickname: str (optional)
        avatar: str (optional)
    
    Note: Email cannot be changed after registration (for security).
          Only admin can change user email via User Management.
    """
    try:
        user_id = getattr(g, 'user_id', None)
        if not user_id:
            return jsonify({'code': 0, 'msg': 'Not authenticated', 'data': None}), 401
        
        data = request.get_json() or {}
        
        # Only allow updating certain fields for self-service
        # Email is NOT allowed to be changed (security: bound to account)
        allowed = {}
        for field in ['nickname', 'avatar']:
            if field in data:
                allowed[field] = data[field]
        
        if not allowed:
            return jsonify({'code': 0, 'msg': 'No valid fields to update', 'data': None}), 400
        
        success = get_user_service().update_user(user_id, allowed)
        
        if success:
            return jsonify({'code': 1, 'msg': 'Profile updated successfully', 'data': None})
        else:
            return jsonify({'code': 0, 'msg': 'Update failed', 'data': None}), 400
    except Exception as e:
        logger.error(f"update_profile failed: {e}")
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


@user_bp.route('/my-credits-log', methods=['GET'])
@login_required
def get_my_credits_log():
    """
    Get current user's credits log.
    
    Query params:
        page: int (default 1)
        page_size: int (default 20)
    """
    try:
        from app.services.billing_service import get_billing_service
        
        user_id = getattr(g, 'user_id', None)
        if not user_id:
            return jsonify({'code': 0, 'msg': 'Not authenticated', 'data': None}), 401
        
        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('page_size', 20, type=int)
        page_size = min(100, max(1, page_size))
        
        result = get_billing_service().get_credits_log(user_id, page, page_size)
        
        return jsonify({'code': 1, 'msg': 'success', 'data': result})
    except Exception as e:
        logger.error(f"get_my_credits_log failed: {e}")
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


@user_bp.route('/my-referrals', methods=['GET'])
@login_required
def get_my_referrals():
    """
    Get list of users referred by current user.
    
    Query params:
        page: int (default 1)
        page_size: int (default 20)
    
    Returns:
        list: Users referred by current user (id, username, nickname, avatar, created_at)
        total: Total count of referrals
        referral_code: Current user's referral code (user ID)
        referral_bonus: Credits earned per referral
        register_bonus: Credits new users get on registration
    """
    try:
        import os
        from app.utils.db import get_db_connection
        
        user_id = getattr(g, 'user_id', None)
        if not user_id:
            return jsonify({'code': 0, 'msg': 'Not authenticated', 'data': None}), 401
        
        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('page_size', 20, type=int)
        page_size = min(100, max(1, page_size))
        offset = (page - 1) * page_size
        
        with get_db_connection() as db:
            cur = db.cursor()
            
            # Get total count
            cur.execute(
                "SELECT COUNT(*) as cnt FROM qd_users WHERE referred_by = ?",
                (user_id,)
            )
            total = cur.fetchone()['cnt']
            
            # Get referral list
            cur.execute(
                """
                SELECT id, username, nickname, avatar, created_at 
                FROM qd_users 
                WHERE referred_by = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (user_id, page_size, offset)
            )
            rows = cur.fetchall()
            cur.close()
            
            referrals = []
            for row in rows:
                referrals.append({
                    'id': row['id'],
                    'username': row['username'],
                    'nickname': row['nickname'],
                    'avatar': row['avatar'],
                    'created_at': row['created_at'].isoformat() if row['created_at'] else None
                })
        
        return jsonify({
            'code': 1,
            'msg': 'success',
            'data': {
                'list': referrals,
                'total': total,
                'page': page,
                'page_size': page_size,
                'referral_code': str(user_id),
                'referral_bonus': int(os.getenv('CREDITS_REFERRAL_BONUS', '0')),
                'register_bonus': int(os.getenv('CREDITS_REGISTER_BONUS', '0'))
            }
        })
    except Exception as e:
        logger.error(f"get_my_referrals failed: {e}")
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


@user_bp.route('/notification-settings', methods=['GET'])
@login_required
def get_notification_settings():
    """
    Get current user's notification settings.
    
    Returns:
        notification_settings: {
            default_channels: ['browser', 'telegram', ...],
            telegram_chat_id: str,
            email: str (optional, override for notifications),
            discord_webhook: str (optional)
        }
    """
    try:
        import json
        from app.utils.db import get_db_connection
        
        user_id = getattr(g, 'user_id', None)
        if not user_id:
            return jsonify({'code': 0, 'msg': 'Not authenticated', 'data': None}), 401
        
        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute("SELECT notification_settings, email FROM qd_users WHERE id = ?", (user_id,))
            row = cur.fetchone()
            cur.close()
        
        if not row:
            return jsonify({'code': 0, 'msg': 'User not found', 'data': None}), 404
        
        # Parse notification_settings JSON
        settings_str = row.get('notification_settings') or ''
        settings = {}
        if settings_str:
            try:
                settings = json.loads(settings_str)
            except Exception:
                settings = {}
        
        # Default values
        if 'default_channels' not in settings:
            settings['default_channels'] = ['browser']
        if 'email' not in settings:
            settings['email'] = row.get('email') or ''
        
        return jsonify({
            'code': 1,
            'msg': 'success',
            'data': settings
        })
    except Exception as e:
        logger.error(f"get_notification_settings failed: {e}")
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


@user_bp.route('/notification-settings', methods=['PUT'])
@login_required
def update_notification_settings():
    """
    Update current user's notification settings.
    
    Request body:
        default_channels: list of str (optional, e.g. ['browser', 'telegram'])
        telegram_bot_token: str (optional, user's own Telegram bot token)
        telegram_chat_id: str (optional)
        email: str (optional, for notification override)
        discord_webhook: str (optional)
    """
    try:
        import json
        from app.utils.db import get_db_connection
        
        user_id = getattr(g, 'user_id', None)
        if not user_id:
            return jsonify({'code': 0, 'msg': 'Not authenticated', 'data': None}), 401
        
        data = request.get_json() or {}
        
        # Validate channels
        valid_channels = ['browser', 'email', 'telegram', 'discord', 'webhook', 'phone']
        default_channels = data.get('default_channels', [])
        if not isinstance(default_channels, list):
            default_channels = ['browser']
        default_channels = [c for c in default_channels if c in valid_channels]
        if not default_channels:
            default_channels = ['browser']
        
        # Build settings object
        settings = {
            'default_channels': default_channels,
            'telegram_bot_token': str(data.get('telegram_bot_token') or '').strip(),
            'telegram_chat_id': str(data.get('telegram_chat_id') or '').strip(),
            'email': str(data.get('email') or '').strip(),
            'discord_webhook': str(data.get('discord_webhook') or '').strip(),
            'webhook_url': str(data.get('webhook_url') or '').strip(),
            'phone': str(data.get('phone') or '').strip(),
        }
        
        # Remove empty values (but keep default_channels and telegram_bot_token even if partially filled)
        settings = {k: v for k, v in settings.items() if v or k == 'default_channels'}
        
        settings_json = json.dumps(settings, ensure_ascii=False)
        
        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute(
                "UPDATE qd_users SET notification_settings = ?, updated_at = NOW() WHERE id = ?",
                (settings_json, user_id)
            )
            db.commit()
            cur.close()
        
        return jsonify({
            'code': 1,
            'msg': 'Notification settings updated',
            'data': settings
        })
    except Exception as e:
        logger.error(f"update_notification_settings failed: {e}")
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


@user_bp.route('/change-password', methods=['POST'])
@login_required
def change_password():
    """
    Change current user's password.
    
    Request body:
        old_password: str (required)
        new_password: str (required)
    """
    try:
        user_id = getattr(g, 'user_id', None)
        if not user_id:
            return jsonify({'code': 0, 'msg': 'Not authenticated', 'data': None}), 401
        
        data = request.get_json() or {}
        old_password = data.get('old_password', '')
        new_password = data.get('new_password', '')
        
        if not new_password:
            return jsonify({'code': 0, 'msg': 'New password required', 'data': None}), 400
        
        if len(new_password) < 6:
            return jsonify({'code': 0, 'msg': 'New password must be at least 6 characters', 'data': None}), 400
        
        # Check if user has a password set
        user_service = get_user_service()
        user = user_service.get_user_by_id(user_id)
        if not user:
            return jsonify({'code': 0, 'msg': 'User not found', 'data': None}), 404
        
        # Get password_hash to check if user has no password
        from app.utils.db import get_db_connection
        with get_db_connection() as db:
            cur = db.cursor()
            cur.execute("SELECT password_hash FROM qd_users WHERE id = ?", (user_id,))
            row = cur.fetchone()
            cur.close()
        
        password_hash = row.get('password_hash', '') if row else ''
        has_password = password_hash and password_hash.strip() != ''
        
        # If user has no password, allow setting password without old password
        if not has_password:
            if not old_password:
                # No old password required for users without password
                success = user_service.reset_password(user_id, new_password)
                if success:
                    return jsonify({'code': 1, 'msg': 'Password set successfully', 'data': None})
                else:
                    return jsonify({'code': 0, 'msg': 'Failed to set password', 'data': None}), 500
            else:
                # If old_password is provided but user has no password, ignore it
                success = user_service.reset_password(user_id, new_password)
                if success:
                    return jsonify({'code': 1, 'msg': 'Password set successfully', 'data': None})
                else:
                    return jsonify({'code': 0, 'msg': 'Failed to set password', 'data': None}), 500
        else:
            # User has existing password, require old password verification
            if not old_password:
                return jsonify({'code': 0, 'msg': 'Old password required', 'data': None}), 400
            
            success = user_service.change_password(user_id, old_password, new_password)
            
            if success:
                return jsonify({'code': 1, 'msg': 'Password changed successfully', 'data': None})
            else:
                return jsonify({'code': 0, 'msg': 'Old password incorrect', 'data': None}), 400
    except ValueError as e:
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 400
    except Exception as e:
        logger.error(f"change_password failed: {e}")
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


# ==================== System Overview (Admin) ====================

def _safe_json_loads(s, default=None):
    """Safely parse JSON string."""
    if not s:
        return default
    if isinstance(s, dict):
        return s
    try:
        return json.loads(s)
    except Exception:
        return default


@user_bp.route('/system-strategies', methods=['GET'])
@login_required
@admin_required
def get_system_strategies():
    """
    Get all strategies across the entire system (admin only).
    Returns strategy details with user info, positions, PnL, indicators, etc.

    Query params:
        page: int (default 1)
        page_size: int (default 20, max 100)
        status: str (optional, filter by status: running/stopped/all)
        search: str (optional, search by strategy name/symbol/username)
    """
    try:
        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('page_size', 20, type=int)
        status_filter = request.args.get('status', '', type=str).strip().lower()
        search = request.args.get('search', '', type=str).strip()
        page_size = min(100, max(1, page_size))
        offset = (page - 1) * page_size

        with get_db_connection() as db:
            cur = db.cursor()

            # Build WHERE clause
            conditions = []
            params = []

            if status_filter and status_filter != 'all':
                conditions.append("s.status = ?")
                params.append(status_filter)

            if search:
                conditions.append(
                    "(s.strategy_name ILIKE ? OR s.symbol ILIKE ? OR u.username ILIKE ? OR u.nickname ILIKE ?)"
                )
                like_val = f"%{search}%"
                params.extend([like_val, like_val, like_val, like_val])

            where_clause = ""
            if conditions:
                where_clause = "WHERE " + " AND ".join(conditions)

            # Get total count
            count_sql = f"""
                SELECT COUNT(*) as cnt
                FROM qd_strategies_trading s
                LEFT JOIN qd_users u ON u.id = s.user_id
                {where_clause}
            """
            cur.execute(count_sql, tuple(params))
            total = cur.fetchone()['cnt']

            # Get strategies with user info
            query_sql = f"""
                SELECT 
                    s.id,
                    s.user_id,
                    s.strategy_name,
                    s.strategy_type,
                    s.market_category,
                    s.execution_mode,
                    s.status,
                    s.symbol,
                    s.timeframe,
                    s.initial_capital,
                    s.leverage,
                    s.market_type,
                    s.indicator_config,
                    s.trading_config,
                    s.exchange_config,
                    s.decide_interval,
                    s.created_at,
                    s.updated_at,
                    u.username,
                    u.nickname
                FROM qd_strategies_trading s
                LEFT JOIN qd_users u ON u.id = s.user_id
                {where_clause}
                ORDER BY s.status DESC, s.updated_at DESC
                LIMIT ? OFFSET ?
            """
            cur.execute(query_sql, tuple(params) + (page_size, offset))
            strategies = cur.fetchall() or []

            # Collect strategy IDs
            strategy_ids = [s['id'] for s in strategies]

            # Batch load positions for these strategies
            positions_map = {}
            if strategy_ids:
                placeholders = ','.join(['?'] * len(strategy_ids))
                cur.execute(
                    f"""
                    SELECT strategy_id, symbol, side, size, entry_price, current_price, 
                           unrealized_pnl, pnl_percent, equity, updated_at
                    FROM qd_strategy_positions
                    WHERE strategy_id IN ({placeholders})
                    ORDER BY strategy_id, updated_at DESC
                    """,
                    tuple(strategy_ids)
                )
                for pos in (cur.fetchall() or []):
                    sid = pos['strategy_id']
                    if sid not in positions_map:
                        positions_map[sid] = []
                    positions_map[sid].append(dict(pos))

            # Batch load recent trade stats (realized PnL per strategy)
            trade_stats_map = {}
            if strategy_ids:
                placeholders = ','.join(['?'] * len(strategy_ids))
                cur.execute(
                    f"""
                    SELECT strategy_id, 
                           COUNT(*) as trade_count, 
                           COALESCE(SUM(profit), 0) as total_realized_pnl
                    FROM qd_strategy_trades
                    WHERE strategy_id IN ({placeholders})
                    GROUP BY strategy_id
                    """,
                    tuple(strategy_ids)
                )
                for row in (cur.fetchall() or []):
                    trade_stats_map[row['strategy_id']] = {
                        'trade_count': row['trade_count'],
                        'total_realized_pnl': float(row['total_realized_pnl'] or 0)
                    }

            cur.close()

        # Build response
        items = []
        for s in strategies:
            sid = s['id']
            indicator_config = _safe_json_loads(s.get('indicator_config'), {})
            trading_config = _safe_json_loads(s.get('trading_config'), {})
            exchange_config = _safe_json_loads(s.get('exchange_config'), {})

            # Extract indicator name
            indicator_name = ''
            if isinstance(indicator_config, dict):
                indicator_name = indicator_config.get('indicator_name') or indicator_config.get('name') or ''

            # Extract exchange name
            exchange_name = ''
            if isinstance(exchange_config, dict):
                exchange_name = exchange_config.get('exchange_id') or exchange_config.get('exchange') or ''

            # Positions data
            positions = positions_map.get(sid, [])
            total_unrealized_pnl = sum(float(p.get('unrealized_pnl') or 0) for p in positions)
            total_equity = sum(float(p.get('equity') or 0) for p in positions)
            position_count = len(positions)

            # Trade stats
            trade_stats = trade_stats_map.get(sid, {'trade_count': 0, 'total_realized_pnl': 0})
            total_realized_pnl = trade_stats['total_realized_pnl']
            trade_count = trade_stats['trade_count']

            # Calculate total PnL and ROI
            initial_capital = float(s.get('initial_capital') or 0)
            total_pnl = total_unrealized_pnl + total_realized_pnl
            roi = (total_pnl / initial_capital * 100) if initial_capital > 0 else 0

            # Cross-sectional info
            cs_type = ''
            symbol_list = []
            if isinstance(trading_config, dict):
                cs_type = trading_config.get('cs_strategy_type') or 'single'
                symbol_list = trading_config.get('symbol_list') or []

            # Format timestamps
            created_at = s.get('created_at')
            updated_at = s.get('updated_at')
            if hasattr(created_at, 'isoformat'):
                created_at = created_at.isoformat()
            if hasattr(updated_at, 'isoformat'):
                updated_at = updated_at.isoformat()

            # Format position timestamps
            for p in positions:
                if hasattr(p.get('updated_at'), 'isoformat'):
                    p['updated_at'] = p['updated_at'].isoformat()

            items.append({
                'id': sid,
                'user_id': s['user_id'],
                'username': s.get('username') or '',
                'nickname': s.get('nickname') or '',
                'strategy_name': s.get('strategy_name') or '',
                'strategy_type': s.get('strategy_type') or '',
                'cs_strategy_type': cs_type,
                'market_category': s.get('market_category') or '',
                'execution_mode': s.get('execution_mode') or '',
                'status': s.get('status') or 'stopped',
                'symbol': s.get('symbol') or '',
                'symbol_list': symbol_list,
                'timeframe': s.get('timeframe') or '',
                'initial_capital': initial_capital,
                'leverage': int(s.get('leverage') or 1),
                'market_type': s.get('market_type') or '',
                'indicator_name': indicator_name,
                'exchange_name': exchange_name,
                'decide_interval': s.get('decide_interval') or 300,
                'position_count': position_count,
                'total_unrealized_pnl': round(total_unrealized_pnl, 4),
                'total_realized_pnl': round(total_realized_pnl, 4),
                'total_pnl': round(total_pnl, 4),
                'total_equity': round(total_equity, 4),
                'roi': round(roi, 2),
                'trade_count': trade_count,
                'positions': positions,
                'created_at': created_at,
                'updated_at': updated_at
            })

        # Compute summary stats from all matched strategies (not just current page items).
        with get_db_connection() as db:
            cur = db.cursor()

            # Aggregate strategy counts/capital by execution mode and running status.
            agg_sql = f"""
                SELECT
                    COUNT(*) AS total_strategies,
                    COALESCE(SUM(s.initial_capital), 0) AS total_capital,
                    COALESCE(SUM(CASE WHEN s.status = 'running' THEN 1 ELSE 0 END), 0) AS running_strategies,
                    COALESCE(SUM(CASE WHEN s.execution_mode = 'live' THEN 1 ELSE 0 END), 0) AS live_strategies,
                    COALESCE(SUM(CASE WHEN s.execution_mode = 'signal' THEN 1 ELSE 0 END), 0) AS signal_strategies,
                    COALESCE(SUM(CASE WHEN s.status = 'running' AND s.execution_mode = 'live' THEN 1 ELSE 0 END), 0) AS running_live_strategies,
                    COALESCE(SUM(CASE WHEN s.status = 'running' AND s.execution_mode = 'signal' THEN 1 ELSE 0 END), 0) AS running_signal_strategies,
                    COALESCE(SUM(CASE WHEN s.execution_mode = 'live' THEN s.initial_capital ELSE 0 END), 0) AS live_capital,
                    COALESCE(SUM(CASE WHEN s.execution_mode = 'signal' THEN s.initial_capital ELSE 0 END), 0) AS signal_capital
                FROM qd_strategies_trading s
                LEFT JOIN qd_users u ON u.id = s.user_id
                {where_clause}
            """
            cur.execute(agg_sql, tuple(params))
            agg_row = cur.fetchone() or {}

            # Aggregate unrealized pnl from current positions.
            unreal_sql = f"""
                SELECT COALESCE(SUM(p.unrealized_pnl), 0) AS total_unrealized,
                       COALESCE(SUM(CASE WHEN s.execution_mode = 'live' THEN p.unrealized_pnl ELSE 0 END), 0) AS live_unrealized,
                       COALESCE(SUM(CASE WHEN s.execution_mode = 'signal' THEN p.unrealized_pnl ELSE 0 END), 0) AS signal_unrealized
                FROM qd_strategy_positions p
                JOIN qd_strategies_trading s ON s.id = p.strategy_id
                LEFT JOIN qd_users u ON u.id = s.user_id
                {where_clause}
            """
            cur.execute(unreal_sql, tuple(params))
            unreal_row = cur.fetchone() or {}

            # Aggregate realized pnl from trade history.
            realized_sql = f"""
                SELECT COALESCE(SUM(t.profit), 0) AS total_realized,
                       COALESCE(SUM(CASE WHEN s.execution_mode = 'live' THEN t.profit ELSE 0 END), 0) AS live_realized,
                       COALESCE(SUM(CASE WHEN s.execution_mode = 'signal' THEN t.profit ELSE 0 END), 0) AS signal_realized
                FROM qd_strategy_trades t
                JOIN qd_strategies_trading s ON s.id = t.strategy_id
                LEFT JOIN qd_users u ON u.id = s.user_id
                {where_clause}
            """
            cur.execute(realized_sql, tuple(params))
            realized_row = cur.fetchone() or {}
            cur.close()

        total_capital = float(agg_row.get('total_capital') or 0)
        total_running = int(agg_row.get('running_strategies') or 0)
        total_system_pnl = float(unreal_row.get('total_unrealized') or 0) + float(realized_row.get('total_realized') or 0)
        live_pnl = float(unreal_row.get('live_unrealized') or 0) + float(realized_row.get('live_realized') or 0)
        signal_pnl = float(unreal_row.get('signal_unrealized') or 0) + float(realized_row.get('signal_realized') or 0)

        return jsonify({
            'code': 1,
            'msg': 'success',
            'data': {
                'items': items,
                'total': total,
                'page': page,
                'page_size': page_size,
                'summary': {
                    'total_strategies': int(agg_row.get('total_strategies') or total),
                    'running_strategies': total_running,
                    'total_capital': round(total_capital, 2),
                    'total_pnl': round(total_system_pnl, 4),
                    'total_roi': round((total_system_pnl / total_capital * 100) if total_capital > 0 else 0, 2),
                    'live_strategies': int(agg_row.get('live_strategies') or 0),
                    'signal_strategies': int(agg_row.get('signal_strategies') or 0),
                    'running_live_strategies': int(agg_row.get('running_live_strategies') or 0),
                    'running_signal_strategies': int(agg_row.get('running_signal_strategies') or 0),
                    'live_capital': round(float(agg_row.get('live_capital') or 0), 2),
                    'signal_capital': round(float(agg_row.get('signal_capital') or 0), 2),
                    'live_pnl': round(live_pnl, 4),
                    'signal_pnl': round(signal_pnl, 4)
                }
            }
        })
    except Exception as e:
        logger.error(f"get_system_strategies failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


# ==================== Admin Orders ====================

@user_bp.route('/admin-orders', methods=['GET'])
@login_required
@admin_required
def get_admin_orders():
    """
    Get all orders across the system (admin only).
    Merges qd_membership_orders and qd_usdt_orders into a unified list.

    Query params:
        page: int (default 1)
        page_size: int (default 20, max 100)
        status: str (optional, filter by status: paid/pending/confirmed/expired/all)
        search: str (optional, search by username/email)
    """
    try:
        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('page_size', 20, type=int)
        status_filter = request.args.get('status', '', type=str).strip().lower()
        search = request.args.get('search', '', type=str).strip()
        page_size = min(100, max(1, page_size))
        offset = (page - 1) * page_size

        with get_db_connection() as db:
            cur = db.cursor()

            # --- USDT Orders (primary) ---
            usdt_conditions = []
            usdt_params = []

            if status_filter and status_filter != 'all':
                usdt_conditions.append("o.status = ?")
                usdt_params.append(status_filter)

            if search:
                usdt_conditions.append("(u.username ILIKE ? OR u.email ILIKE ? OR u.nickname ILIKE ?)")
                like_val = f"%{search}%"
                usdt_params.extend([like_val, like_val, like_val])

            usdt_where = ""
            if usdt_conditions:
                usdt_where = "WHERE " + " AND ".join(usdt_conditions)

            # Count
            cur.execute(
                f"SELECT COUNT(*) as cnt FROM qd_usdt_orders o LEFT JOIN qd_users u ON u.id = o.user_id {usdt_where}",
                tuple(usdt_params)
            )
            usdt_total = cur.fetchone()['cnt']

            # --- Membership Orders (mock) ---
            mock_conditions = []
            mock_params = []

            if status_filter and status_filter != 'all':
                mock_conditions.append("m.status = ?")
                mock_params.append(status_filter)

            if search:
                mock_conditions.append("(u.username ILIKE ? OR u.email ILIKE ? OR u.nickname ILIKE ?)")
                like_val = f"%{search}%"
                mock_params.extend([like_val, like_val, like_val])

            mock_where = ""
            if mock_conditions:
                mock_where = "WHERE " + " AND ".join(mock_conditions)

            cur.execute(
                f"SELECT COUNT(*) as cnt FROM qd_membership_orders m LEFT JOIN qd_users u ON u.id = m.user_id {mock_where}",
                tuple(mock_params)
            )
            mock_total = cur.fetchone()['cnt']

            total = usdt_total + mock_total

            # Use UNION ALL to merge both tables into one sorted list
            # We select a unified schema
            union_sql = f"""
                SELECT * FROM (
                    SELECT
                        o.id,
                        'usdt' AS order_type,
                        o.user_id,
                        u.username,
                        u.nickname,
                        u.email AS user_email,
                        o.plan,
                        o.amount_usdt AS amount,
                        'USDT' AS currency,
                        o.chain,
                        o.address,
                        o.tx_hash,
                        o.status,
                        o.created_at,
                        o.paid_at,
                        o.confirmed_at,
                        o.expires_at
                    FROM qd_usdt_orders o
                    LEFT JOIN qd_users u ON u.id = o.user_id
                    {usdt_where}

                    UNION ALL

                    SELECT
                        m.id,
                        'mock' AS order_type,
                        m.user_id,
                        u.username,
                        u.nickname,
                        u.email AS user_email,
                        m.plan,
                        m.price_usd AS amount,
                        'USD' AS currency,
                        '' AS chain,
                        '' AS address,
                        '' AS tx_hash,
                        m.status,
                        m.created_at,
                        m.paid_at,
                        NULL AS confirmed_at,
                        NULL AS expires_at
                    FROM qd_membership_orders m
                    LEFT JOIN qd_users u ON u.id = m.user_id
                    {mock_where}
                ) AS combined
                ORDER BY combined.created_at DESC
                LIMIT ? OFFSET ?
            """
            all_params = list(usdt_params) + list(mock_params) + [page_size, offset]
            cur.execute(union_sql, tuple(all_params))
            rows = cur.fetchall() or []

            # Summary stats
            cur.execute(
                f"""SELECT
                    COUNT(*) AS total_orders,
                    COALESCE(SUM(CASE WHEN status IN ('paid','confirmed') THEN 1 ELSE 0 END), 0) AS paid_orders,
                    COALESCE(SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END), 0) AS pending_orders,
                    COALESCE(SUM(CASE WHEN status IN ('expired','cancelled','failed') THEN 1 ELSE 0 END), 0) AS failed_orders,
                    COALESCE(SUM(CASE WHEN status IN ('paid','confirmed') THEN amount_usdt ELSE 0 END), 0) AS total_revenue
                FROM qd_usdt_orders"""
            )
            summary_row = cur.fetchone() or {}

            cur.close()

        items = []
        for row in rows:
            created_at = row.get('created_at')
            paid_at = row.get('paid_at')
            confirmed_at = row.get('confirmed_at')
            expires_at = row.get('expires_at')
            if hasattr(created_at, 'isoformat'):
                created_at = created_at.isoformat()
            if hasattr(paid_at, 'isoformat'):
                paid_at = paid_at.isoformat()
            if hasattr(confirmed_at, 'isoformat'):
                confirmed_at = confirmed_at.isoformat()
            if hasattr(expires_at, 'isoformat'):
                expires_at = expires_at.isoformat()

            items.append({
                'id': row['id'],
                'order_type': row.get('order_type') or '',
                'user_id': row.get('user_id'),
                'username': row.get('username') or '',
                'nickname': row.get('nickname') or '',
                'user_email': row.get('user_email') or '',
                'plan': row.get('plan') or '',
                'amount': float(row.get('amount') or 0),
                'currency': row.get('currency') or '',
                'chain': row.get('chain') or '',
                'address': row.get('address') or '',
                'tx_hash': row.get('tx_hash') or '',
                'status': row.get('status') or '',
                'created_at': created_at,
                'paid_at': paid_at,
                'confirmed_at': confirmed_at,
                'expires_at': expires_at
            })

        return jsonify({
            'code': 1,
            'msg': 'success',
            'data': {
                'items': items,
                'total': total,
                'page': page,
                'page_size': page_size,
                'summary': {
                    'total_orders': int(summary_row.get('total_orders') or 0),
                    'paid_orders': int(summary_row.get('paid_orders') or 0),
                    'pending_orders': int(summary_row.get('pending_orders') or 0),
                    'failed_orders': int(summary_row.get('failed_orders') or 0),
                    'total_revenue': round(float(summary_row.get('total_revenue') or 0), 2)
                }
            }
        })
    except Exception as e:
        logger.error(f"get_admin_orders failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500


# ==================== Admin AI Analysis Stats ====================

@user_bp.route('/admin-ai-stats', methods=['GET'])
@login_required
@admin_required
def get_admin_ai_stats():
    """
    Get AI analysis usage statistics across the system (admin only).
    Does NOT expose analysis results, only aggregated counts/stats.

    Query params:
        page: int (default 1)
        page_size: int (default 20, max 100)
        search: str (optional, search by username)
    """
    try:
        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('page_size', 20, type=int)
        search = request.args.get('search', '', type=str).strip()
        page_size = min(100, max(1, page_size))
        offset = (page - 1) * page_size

        with get_db_connection() as db:
            cur = db.cursor()

            # --- Overall summary (from qd_analysis_tasks + qd_analysis_memory) ---
            cur.execute("""
                SELECT
                    COUNT(*) AS total_tasks,
                    COUNT(DISTINCT user_id) AS unique_users,
                    COUNT(DISTINCT symbol) AS unique_symbols,
                    COUNT(DISTINCT market) AS unique_markets
                FROM qd_analysis_tasks
            """)
            task_summary = cur.fetchone() or {}

            memory_summary = {}
            try:
                cur.execute("""
                    SELECT
                        COUNT(*) AS total_memory,
                        COALESCE(SUM(CASE WHEN was_correct = true THEN 1 ELSE 0 END), 0) AS correct_count,
                        COALESCE(SUM(CASE WHEN was_correct = false THEN 1 ELSE 0 END), 0) AS incorrect_count,
                        COALESCE(SUM(CASE WHEN user_feedback = 'helpful' THEN 1 ELSE 0 END), 0) AS helpful_count,
                        COALESCE(SUM(CASE WHEN user_feedback = 'not_helpful' THEN 1 ELSE 0 END), 0) AS not_helpful_count
                    FROM qd_analysis_memory
                """)
                memory_summary = cur.fetchone() or {}
            except Exception as mem_err:
                logger.warning(f"qd_analysis_memory query failed (table/column may not exist): {mem_err}")
                db.rollback()
                cur = db.cursor()  # re-create cursor after rollback
                memory_summary = {}

            # --- Per-user stats ---
            # Build WHERE clause for user search (applied after JOIN)
            user_where_clause = ""
            user_params = []
            if search:
                user_where_clause = "WHERE (u.username ILIKE ? OR u.nickname ILIKE ? OR u.email ILIKE ?)"
                like_val = f"%{search.strip()}%"
                user_params = [like_val, like_val, like_val]

            # Count distinct users who have analysis records (matching search criteria)
            count_sql = f"""
                SELECT COUNT(DISTINCT t.user_id) AS cnt
                FROM qd_analysis_tasks t
                LEFT JOIN qd_users u ON u.id = t.user_id
                {user_where_clause}
            """
            cur.execute(count_sql, tuple(user_params))
            count_result = cur.fetchone()
            user_total = count_result['cnt'] if count_result else 0

            # Get per-user aggregated stats
            # Important: Filter by user search criteria AFTER grouping, but we need to apply it in WHERE
            # Since we're grouping by user fields, we need to filter before GROUP BY
            stats_sql = f"""
                SELECT
                    t.user_id,
                    u.username,
                    u.nickname,
                    u.email,
                    COUNT(*) AS analysis_count,
                    COUNT(DISTINCT t.symbol) AS symbol_count,
                    COUNT(DISTINCT t.market) AS market_count,
                    MAX(t.created_at) AS last_analysis_at,
                    MIN(t.created_at) AS first_analysis_at
                FROM qd_analysis_tasks t
                LEFT JOIN qd_users u ON u.id = t.user_id
                {user_where_clause}
                GROUP BY t.user_id, u.username, u.nickname, u.email
                ORDER BY analysis_count DESC
                LIMIT ? OFFSET ?
            """
            cur.execute(stats_sql, tuple(user_params) + (page_size, offset))
            user_rows = cur.fetchall() or []

            # Get per-user analysis_memory stats (correct/helpful counts)
            user_ids = [r['user_id'] for r in user_rows if r.get('user_id')]
            memory_stats_map = {}
            if user_ids:
                try:
                    placeholders = ','.join(['?'] * len(user_ids))
                    cur.execute(
                        f"""
                        SELECT
                            user_id,
                            COUNT(*) AS memory_count,
                            COALESCE(SUM(CASE WHEN was_correct = true THEN 1 ELSE 0 END), 0) AS correct,
                            COALESCE(SUM(CASE WHEN was_correct = false THEN 1 ELSE 0 END), 0) AS incorrect,
                            COALESCE(SUM(CASE WHEN user_feedback = 'helpful' THEN 1 ELSE 0 END), 0) AS helpful,
                            COALESCE(SUM(CASE WHEN user_feedback = 'not_helpful' THEN 1 ELSE 0 END), 0) AS not_helpful
                        FROM qd_analysis_memory
                        WHERE user_id IN ({placeholders})
                        GROUP BY user_id
                        """,
                        tuple(user_ids)
                    )
                    for row in (cur.fetchall() or []):
                        memory_stats_map[row['user_id']] = {
                            'memory_count': row['memory_count'],
                            'correct': row['correct'],
                            'incorrect': row['incorrect'],
                            'helpful': row['helpful'],
                            'not_helpful': row['not_helpful']
                        }
                except Exception as mem_err:
                    logger.warning(f"qd_analysis_memory per-user query failed: {mem_err}")
                    db.rollback()
                    cur = db.cursor()  # re-create cursor after rollback
                    memory_stats_map = {}

            # Get recent analysis records (last 50)
            # Ensure we get user info even if user_id is NULL or user doesn't exist
            cur.execute(
                """
                SELECT
                    t.id,
                    t.user_id,
                    COALESCE(u.username, '') AS username,
                    COALESCE(u.nickname, '') AS nickname,
                    COALESCE(u.email, '') AS email,
                    t.market,
                    t.symbol,
                    t.model,
                    t.status,
                    t.created_at,
                    t.completed_at
                FROM qd_analysis_tasks t
                LEFT JOIN qd_users u ON u.id = t.user_id
                WHERE t.user_id IS NOT NULL
                ORDER BY t.created_at DESC
                LIMIT 50
                """
            )
            recent_rows = cur.fetchall() or []

            cur.close()

        # Build per-user items
        user_items = []
        for row in user_rows:
            uid = row.get('user_id')
            if not uid:  # Skip rows with NULL user_id
                continue
                
            ms = memory_stats_map.get(uid, {})
            last_at = row.get('last_analysis_at')
            first_at = row.get('first_analysis_at')
            
            # Convert datetime to ISO format string if needed
            if last_at and hasattr(last_at, 'isoformat'):
                last_at = last_at.isoformat()
            elif last_at:
                last_at = str(last_at)
            else:
                last_at = None
                
            if first_at and hasattr(first_at, 'isoformat'):
                first_at = first_at.isoformat()
            elif first_at:
                first_at = str(first_at)
            else:
                first_at = None

            user_items.append({
                'user_id': int(uid),
                'username': str(row.get('username') or ''),
                'nickname': str(row.get('nickname') or ''),
                'email': str(row.get('email') or ''),
                'analysis_count': int(row.get('analysis_count') or 0),
                'symbol_count': int(row.get('symbol_count') or 0),
                'market_count': int(row.get('market_count') or 0),
                'correct': int(ms.get('correct', 0)),
                'incorrect': int(ms.get('incorrect', 0)),
                'helpful': int(ms.get('helpful', 0)),
                'not_helpful': int(ms.get('not_helpful', 0)),
                'last_analysis_at': last_at,
                'first_analysis_at': first_at
            })

        # Build recent records
        recent_items = []
        for row in recent_rows:
            user_id = row.get('user_id')
            if not user_id:  # Skip rows with NULL user_id
                continue
                
            created_at = row.get('created_at')
            completed_at = row.get('completed_at')
            
            # Convert datetime to ISO format string if needed
            if created_at and hasattr(created_at, 'isoformat'):
                created_at = created_at.isoformat()
            elif created_at:
                created_at = str(created_at)
            else:
                created_at = None
                
            if completed_at and hasattr(completed_at, 'isoformat'):
                completed_at = completed_at.isoformat()
            elif completed_at:
                completed_at = str(completed_at)
            else:
                completed_at = None

            recent_items.append({
                'id': int(row.get('id') or 0),
                'user_id': int(user_id),
                'username': str(row.get('username') or ''),
                'nickname': str(row.get('nickname') or ''),
                'email': str(row.get('email') or ''),
                'market': str(row.get('market') or ''),
                'symbol': str(row.get('symbol') or ''),
                'model': str(row.get('model') or ''),
                'status': str(row.get('status') or ''),
                'created_at': created_at,
                'completed_at': completed_at
            })

        return jsonify({
            'code': 1,
            'msg': 'success',
            'data': {
                'user_stats': user_items,
                'user_total': user_total,
                'page': page,
                'page_size': page_size,
                'recent': recent_items,
                'summary': {
                    'total_analyses': int(task_summary.get('total_tasks') or 0),
                    'unique_users': int(task_summary.get('unique_users') or 0),
                    'unique_symbols': int(task_summary.get('unique_symbols') or 0),
                    'unique_markets': int(task_summary.get('unique_markets') or 0),
                    'total_memory': int(memory_summary.get('total_memory') or 0),
                    'correct_count': int(memory_summary.get('correct_count') or 0),
                    'incorrect_count': int(memory_summary.get('incorrect_count') or 0),
                    'helpful_count': int(memory_summary.get('helpful_count') or 0),
                    'not_helpful_count': int(memory_summary.get('not_helpful_count') or 0)
                }
            }
        })
    except Exception as e:
        logger.error(f"get_admin_ai_stats failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'code': 0, 'msg': str(e), 'data': None}), 500