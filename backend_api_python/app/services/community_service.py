"""
Community Service - 指标社区服务

处理指标市场、购买、评论等功能。
"""
import json
import time
from decimal import Decimal
from typing import Dict, Any, List, Optional, Tuple

from app.utils.db import get_db_connection
from app.utils.logger import get_logger
from app.services.billing_service import get_billing_service

logger = get_logger(__name__)


class CommunityService:
    """指标社区服务类"""
    
    def __init__(self):
        self.billing = get_billing_service()
        # Best-effort: ensure vip_free column exists (for old databases)
        try:
            with get_db_connection() as db:
                cur = db.cursor()
                cur.execute("ALTER TABLE qd_indicator_codes ADD COLUMN IF NOT EXISTS vip_free BOOLEAN DEFAULT FALSE")
                db.commit()
                cur.close()
        except Exception:
            pass
    
    # ==========================================
    # 指标市场
    # ==========================================
    
    def get_market_indicators(
        self,
        page: int = 1,
        page_size: int = 12,
        keyword: str = None,
        pricing_type: str = None,  # 'free' / 'paid' / None(all)
        sort_by: str = 'newest',   # 'newest' / 'hot' / 'price_asc' / 'price_desc' / 'rating'
        user_id: int = None        # 当前用户ID，用于判断是否已购买
    ) -> Dict[str, Any]:
        """获取市场上已发布的指标列表"""
        offset = (page - 1) * page_size
        
        try:
            with get_db_connection() as db:
                cur = db.cursor()
                
                # 构建查询条件 - 只显示已发布且审核通过的指标
                where_clauses = ["i.publish_to_community = 1", "(i.review_status = 'approved' OR i.review_status IS NULL)"]
                params = []
                
                if keyword and keyword.strip():
                    where_clauses.append("(i.name ILIKE ? OR i.description ILIKE ?)")
                    search_term = f"%{keyword.strip()}%"
                    params.extend([search_term, search_term])
                
                if pricing_type == 'free':
                    where_clauses.append("(i.pricing_type = 'free' OR i.price <= 0)")
                elif pricing_type == 'paid':
                    where_clauses.append("(i.pricing_type != 'free' AND i.price > 0)")
                
                where_sql = " AND ".join(where_clauses)
                
                # 排序
                order_map = {
                    'newest': 'i.created_at DESC',
                    'hot': 'i.purchase_count DESC, i.view_count DESC',
                    'price_asc': 'i.price ASC, i.created_at DESC',
                    'price_desc': 'i.price DESC, i.created_at DESC',
                    'rating': 'i.avg_rating DESC, i.rating_count DESC'
                }
                order_sql = order_map.get(sort_by, 'i.created_at DESC')
                
                # 获取总数
                count_sql = f"""
                    SELECT COUNT(*) as count 
                    FROM qd_indicator_codes i 
                    WHERE {where_sql}
                """
                cur.execute(count_sql, tuple(params))
                total = cur.fetchone()['count']
                
                # 获取列表（联表查询作者信息）
                query_sql = f"""
                    SELECT 
                        i.id, i.name, i.description, i.pricing_type, i.price, COALESCE(i.vip_free, FALSE) as vip_free,
                        i.preview_image, i.purchase_count, i.avg_rating, i.rating_count,
                        i.view_count, i.created_at, i.updated_at,
                        u.id as author_id, u.username as author_username, 
                        u.nickname as author_nickname, u.avatar as author_avatar
                    FROM qd_indicator_codes i
                    LEFT JOIN qd_users u ON i.user_id = u.id
                    WHERE {where_sql}
                    ORDER BY {order_sql}
                    LIMIT ? OFFSET ?
                """
                cur.execute(query_sql, tuple(params + [page_size, offset]))
                rows = cur.fetchall() or []
                
                # 如果有当前用户，查询已购买的指标
                purchased_ids = set()
                if user_id:
                    indicator_ids = [r['id'] for r in rows]
                    if indicator_ids:
                        placeholders = ','.join(['?'] * len(indicator_ids))
                        cur.execute(
                            f"SELECT indicator_id FROM qd_indicator_purchases WHERE buyer_id = ? AND indicator_id IN ({placeholders})",
                            tuple([user_id] + indicator_ids)
                        )
                        purchased_ids = {r['indicator_id'] for r in (cur.fetchall() or [])}
                
                cur.close()
                
                # 格式化返回数据
                items = []
                for row in rows:
                    items.append({
                        'id': row['id'],
                        'name': row['name'],
                        'description': row['description'][:200] if row['description'] else '',
                        'pricing_type': row['pricing_type'] or 'free',
                        'price': float(row['price'] or 0),
                        'vip_free': bool(row.get('vip_free') or False),
                        'preview_image': row['preview_image'] or '',
                        'purchase_count': row['purchase_count'] or 0,
                        'avg_rating': float(row['avg_rating'] or 0),
                        'rating_count': row['rating_count'] or 0,
                        'view_count': row['view_count'] or 0,
                        'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                        'author': {
                            'id': row['author_id'],
                            'username': row['author_username'],
                            'nickname': row['author_nickname'] or row['author_username'],
                            'avatar': row['author_avatar'] or '/avatar2.jpg'
                        },
                        'is_purchased': row['id'] in purchased_ids,
                        'is_own': row['author_id'] == user_id
                    })
                
                return {
                    'items': items,
                    'total': total,
                    'page': page,
                    'page_size': page_size,
                    'total_pages': (total + page_size - 1) // page_size if total > 0 else 0
                }
                
        except Exception as e:
            logger.error(f"get_market_indicators failed: {e}")
            return {'items': [], 'total': 0, 'page': 1, 'page_size': page_size, 'total_pages': 0}
    
    def get_indicator_detail(self, indicator_id: int, user_id: int = None) -> Optional[Dict[str, Any]]:
        """获取指标详情"""
        try:
            with get_db_connection() as db:
                cur = db.cursor()
                
                # 获取指标信息
                cur.execute("""
                    SELECT 
                        i.id, i.name, i.description, i.pricing_type, i.price, COALESCE(i.vip_free, FALSE) as vip_free,
                        i.preview_image, i.purchase_count, i.avg_rating, i.rating_count,
                        i.view_count, i.publish_to_community, i.created_at, i.updated_at,
                        i.user_id,
                        u.id as author_id, u.username as author_username, 
                        u.nickname as author_nickname, u.avatar as author_avatar
                    FROM qd_indicator_codes i
                    LEFT JOIN qd_users u ON i.user_id = u.id
                    WHERE i.id = ?
                """, (indicator_id,))
                row = cur.fetchone()
                
                if not row:
                    cur.close()
                    return None
                
                # 检查是否已发布到社区（或者是自己的指标）
                if not row['publish_to_community'] and row['user_id'] != user_id:
                    cur.close()
                    return None
                
                # 检查是否已购买
                is_purchased = False
                if user_id:
                    cur.execute(
                        "SELECT id FROM qd_indicator_purchases WHERE indicator_id = ? AND buyer_id = ?",
                        (indicator_id, user_id)
                    )
                    is_purchased = cur.fetchone() is not None
                
                # 增加浏览次数
                cur.execute(
                    "UPDATE qd_indicator_codes SET view_count = COALESCE(view_count, 0) + 1 WHERE id = ?",
                    (indicator_id,)
                )
                db.commit()
                cur.close()
                
                return {
                    'id': row['id'],
                    'name': row['name'],
                    'description': row['description'] or '',
                    'pricing_type': row['pricing_type'] or 'free',
                    'price': float(row['price'] or 0),
                    'vip_free': bool(row.get('vip_free') or False),
                    'preview_image': row['preview_image'] or '',
                    'purchase_count': row['purchase_count'] or 0,
                    'avg_rating': float(row['avg_rating'] or 0),
                    'rating_count': row['rating_count'] or 0,
                    'view_count': (row['view_count'] or 0) + 1,
                    'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                    'updated_at': row['updated_at'].isoformat() if row['updated_at'] else None,
                    'author': {
                        'id': row['author_id'],
                        'username': row['author_username'],
                        'nickname': row['author_nickname'] or row['author_username'],
                        'avatar': row['author_avatar'] or '/avatar2.jpg'
                    },
                    'is_purchased': is_purchased,
                    'is_own': row['user_id'] == user_id
                }
                
        except Exception as e:
            logger.error(f"get_indicator_detail failed: {e}")
            return None
    
    # ==========================================
    # 购买功能
    # ==========================================
    
    def purchase_indicator(self, buyer_id: int, indicator_id: int) -> Tuple[bool, str, Dict[str, Any]]:
        """
        购买指标
        
        Returns:
            (success, message, data)
        """
        try:
            with get_db_connection() as db:
                cur = db.cursor()
                
                # 1. 获取指标信息
                cur.execute("""
                    SELECT id, user_id, name, code, description, pricing_type, price, COALESCE(vip_free, FALSE) as vip_free,
                           preview_image, is_encrypted
                    FROM qd_indicator_codes
                    WHERE id = ? AND publish_to_community = 1
                """, (indicator_id,))
                indicator = cur.fetchone()
                
                if not indicator:
                    cur.close()
                    return False, 'indicator_not_found', {}
                
                seller_id = indicator['user_id']
                price = float(indicator['price'] or 0)
                pricing_type = indicator['pricing_type'] or 'free'
                vip_free = bool(indicator.get('vip_free') or False)
                is_vip, _ = self.billing.get_user_vip_status(buyer_id)

                # VIP-free indicator: VIP users can get it without credits charge
                effective_price = 0.0 if (vip_free and is_vip) else price
                
                # 2. 检查是否购买自己的指标
                if seller_id == buyer_id:
                    cur.close()
                    return False, 'cannot_buy_own', {}
                
                # 3. 检查是否已购买
                cur.execute(
                    "SELECT id FROM qd_indicator_purchases WHERE indicator_id = ? AND buyer_id = ?",
                    (indicator_id, buyer_id)
                )
                if cur.fetchone():
                    cur.close()
                    return False, 'already_purchased', {}
                
                # 4. 如果是付费指标，检查并扣除积分
                if pricing_type != 'free' and effective_price > 0:
                    buyer_credits = self.billing.get_user_credits(buyer_id)
                    if buyer_credits < effective_price:
                        cur.close()
                        return False, 'insufficient_credits', {
                            'required': effective_price,
                            'current': float(buyer_credits)
                        }
                    
                    # 扣除买家积分
                    new_buyer_balance = buyer_credits - Decimal(str(effective_price))
                    cur.execute(
                        "UPDATE qd_users SET credits = ?, updated_at = NOW() WHERE id = ?",
                        (float(new_buyer_balance), buyer_id)
                    )
                    
                    # 记录买家积分日志
                    cur.execute("""
                        INSERT INTO qd_credits_log 
                        (user_id, action, amount, balance_after, feature, reference_id, remark, created_at)
                        VALUES (?, 'indicator_purchase', ?, ?, 'indicator_purchase', ?, ?, NOW())
                    """, (buyer_id, -effective_price, float(new_buyer_balance), str(indicator_id), 
                          f"购买指标: {indicator['name']}"))
                    
                    # 给卖家增加积分（可配置抽成比例，这里先100%给卖家）
                    seller_credits = self.billing.get_user_credits(seller_id)
                    new_seller_balance = seller_credits + Decimal(str(effective_price))
                    cur.execute(
                        "UPDATE qd_users SET credits = ?, updated_at = NOW() WHERE id = ?",
                        (float(new_seller_balance), seller_id)
                    )
                    
                    # 记录卖家积分日志
                    cur.execute("""
                        INSERT INTO qd_credits_log 
                        (user_id, action, amount, balance_after, feature, reference_id, remark, created_at)
                        VALUES (?, 'indicator_sale', ?, ?, 'indicator_sale', ?, ?, NOW())
                    """, (seller_id, effective_price, float(new_seller_balance), str(indicator_id),
                          f"出售指标: {indicator['name']}"))
                
                # 5. 创建购买记录
                cur.execute("""
                    INSERT INTO qd_indicator_purchases 
                    (indicator_id, buyer_id, seller_id, price, created_at)
                    VALUES (?, ?, ?, ?, NOW())
                """, (indicator_id, buyer_id, seller_id, effective_price))
                
                # 6. 复制指标到买家账户
                now_ts = int(time.time())
                # Get vip_free as boolean from indicator
                vip_free_value = bool(indicator.get('vip_free') or False)
                cur.execute("""
                    INSERT INTO qd_indicator_codes
                    (user_id, is_buy, end_time, name, code, description,
                     publish_to_community, pricing_type, price, is_encrypted, preview_image, vip_free,
                     createtime, updatetime, created_at, updated_at)
                    VALUES (?, 1, 0, ?, ?, ?, 0, 'free', 0, ?, ?, ?, ?, ?, NOW(), NOW())
                """, (
                    buyer_id,
                    indicator['name'],
                    indicator['code'],
                    indicator['description'],
                    indicator['is_encrypted'] or 0,
                    indicator['preview_image'],
                    vip_free_value,  # Use boolean value instead of integer 0
                    now_ts, now_ts
                ))
                
                # 7. 更新指标购买次数
                cur.execute("""
                    UPDATE qd_indicator_codes 
                    SET purchase_count = COALESCE(purchase_count, 0) + 1 
                    WHERE id = ?
                """, (indicator_id,))
                
                db.commit()
                cur.close()
                
                logger.info(f"User {buyer_id} purchased indicator {indicator_id} for {effective_price} credits (vip_free={vip_free}, is_vip={is_vip})")
                return True, 'success', {'indicator_name': indicator['name'], 'price': price, 'charged': effective_price, 'vip_free': vip_free}
                
        except Exception as e:
            logger.error(f"purchase_indicator failed: {e}")
            return False, f'error: {str(e)}', {}
    
    def get_my_purchases(self, user_id: int, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        """获取用户购买的指标列表"""
        offset = (page - 1) * page_size
        
        try:
            with get_db_connection() as db:
                cur = db.cursor()
                
                # 获取总数
                cur.execute(
                    "SELECT COUNT(*) as count FROM qd_indicator_purchases WHERE buyer_id = ?",
                    (user_id,)
                )
                total = cur.fetchone()['count']
                
                # 获取列表
                cur.execute("""
                    SELECT 
                        p.id as purchase_id, p.price as purchase_price, p.created_at as purchase_time,
                        i.id, i.name, i.description, i.preview_image, i.avg_rating,
                        u.nickname as seller_nickname, u.avatar as seller_avatar
                    FROM qd_indicator_purchases p
                    LEFT JOIN qd_indicator_codes i ON p.indicator_id = i.id
                    LEFT JOIN qd_users u ON p.seller_id = u.id
                    WHERE p.buyer_id = ?
                    ORDER BY p.created_at DESC
                    LIMIT ? OFFSET ?
                """, (user_id, page_size, offset))
                rows = cur.fetchall() or []
                cur.close()
                
                items = []
                for row in rows:
                    items.append({
                        'purchase_id': row['purchase_id'],
                        'purchase_price': float(row['purchase_price'] or 0),
                        'purchase_time': row['purchase_time'].isoformat() if row['purchase_time'] else None,
                        'indicator': {
                            'id': row['id'],
                            'name': row['name'],
                            'description': row['description'][:100] if row['description'] else '',
                            'preview_image': row['preview_image'] or '',
                            'avg_rating': float(row['avg_rating'] or 0)
                        },
                        'seller': {
                            'nickname': row['seller_nickname'],
                            'avatar': row['seller_avatar'] or '/avatar2.jpg'
                        }
                    })
                
                return {
                    'items': items,
                    'total': total,
                    'page': page,
                    'page_size': page_size,
                    'total_pages': (total + page_size - 1) // page_size if total > 0 else 0
                }
                
        except Exception as e:
            logger.error(f"get_my_purchases failed: {e}")
            return {'items': [], 'total': 0, 'page': 1, 'page_size': page_size, 'total_pages': 0}
    
    # ==========================================
    # 评论功能
    # ==========================================
    
    def get_comments(self, indicator_id: int, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        """获取指标评论列表"""
        offset = (page - 1) * page_size
        
        try:
            with get_db_connection() as db:
                cur = db.cursor()
                
                # 获取总数（只统计一级评论）
                cur.execute("""
                    SELECT COUNT(*) as count FROM qd_indicator_comments 
                    WHERE indicator_id = ? AND parent_id IS NULL AND is_deleted = 0
                """, (indicator_id,))
                total = cur.fetchone()['count']
                
                # 获取评论列表
                cur.execute("""
                    SELECT 
                        c.id, c.rating, c.content, c.created_at,
                        u.id as user_id, u.nickname, u.avatar
                    FROM qd_indicator_comments c
                    LEFT JOIN qd_users u ON c.user_id = u.id
                    WHERE c.indicator_id = ? AND c.parent_id IS NULL AND c.is_deleted = 0
                    ORDER BY c.created_at DESC
                    LIMIT ? OFFSET ?
                """, (indicator_id, page_size, offset))
                rows = cur.fetchall() or []
                cur.close()
                
                items = []
                for row in rows:
                    items.append({
                        'id': row['id'],
                        'rating': row['rating'],
                        'content': row['content'],
                        'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                        'user': {
                            'id': row['user_id'],
                            'nickname': row['nickname'],
                            'avatar': row['avatar'] or '/avatar2.jpg'
                        }
                    })
                
                return {
                    'items': items,
                    'total': total,
                    'page': page,
                    'page_size': page_size,
                    'total_pages': (total + page_size - 1) // page_size if total > 0 else 0
                }
                
        except Exception as e:
            logger.error(f"get_comments failed: {e}")
            return {'items': [], 'total': 0, 'page': 1, 'page_size': page_size, 'total_pages': 0}
    
    def add_comment(
        self, 
        user_id: int, 
        indicator_id: int, 
        rating: int, 
        content: str
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        添加评论（只有购买过的用户可以评论，且只能评论一次）
        """
        try:
            # 验证评分范围
            rating = max(1, min(5, int(rating)))
            content = (content or '').strip()[:500]  # 限制500字
            
            with get_db_connection() as db:
                cur = db.cursor()
                
                # 检查指标是否存在
                cur.execute(
                    "SELECT id, user_id FROM qd_indicator_codes WHERE id = ? AND publish_to_community = 1",
                    (indicator_id,)
                )
                indicator = cur.fetchone()
                if not indicator:
                    cur.close()
                    return False, 'indicator_not_found', {}
                
                # 不能评论自己的指标
                if indicator['user_id'] == user_id:
                    cur.close()
                    return False, 'cannot_comment_own', {}
                
                # 检查是否已购买（免费指标也需要"获取"才能评论）
                cur.execute(
                    "SELECT id FROM qd_indicator_purchases WHERE indicator_id = ? AND buyer_id = ?",
                    (indicator_id, user_id)
                )
                if not cur.fetchone():
                    cur.close()
                    return False, 'not_purchased', {}
                
                # 检查是否已评论
                cur.execute(
                    "SELECT id FROM qd_indicator_comments WHERE indicator_id = ? AND user_id = ? AND parent_id IS NULL",
                    (indicator_id, user_id)
                )
                if cur.fetchone():
                    cur.close()
                    return False, 'already_commented', {}
                
                # 添加评论
                cur.execute("""
                    INSERT INTO qd_indicator_comments 
                    (indicator_id, user_id, rating, content, created_at, updated_at)
                    VALUES (?, ?, ?, ?, NOW(), NOW())
                """, (indicator_id, user_id, rating, content))
                comment_id = cur.lastrowid
                
                # 更新指标的评分统计
                cur.execute("""
                    UPDATE qd_indicator_codes 
                    SET 
                        rating_count = COALESCE(rating_count, 0) + 1,
                        avg_rating = (
                            SELECT AVG(rating) FROM qd_indicator_comments 
                            WHERE indicator_id = ? AND parent_id IS NULL AND is_deleted = 0
                        )
                    WHERE id = ?
                """, (indicator_id, indicator_id))
                
                db.commit()
                cur.close()
                
                logger.info(f"User {user_id} commented on indicator {indicator_id} with rating {rating}")
                return True, 'success', {'comment_id': comment_id}
                
        except Exception as e:
            logger.error(f"add_comment failed: {e}")
            return False, f'error: {str(e)}', {}
    
    def update_comment(
        self,
        user_id: int,
        comment_id: int,
        indicator_id: int,
        rating: int,
        content: str
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        更新评论（只能修改自己的评论）
        """
        try:
            rating = max(1, min(5, int(rating)))
            content = (content or '').strip()[:500]
            
            with get_db_connection() as db:
                cur = db.cursor()
                
                # 检查评论是否存在且属于当前用户
                cur.execute("""
                    SELECT id, rating as old_rating FROM qd_indicator_comments 
                    WHERE id = ? AND user_id = ? AND indicator_id = ? AND is_deleted = 0
                """, (comment_id, user_id, indicator_id))
                comment = cur.fetchone()
                
                if not comment:
                    cur.close()
                    return False, 'comment_not_found', {}
                
                old_rating = comment['old_rating']
                
                # 更新评论
                cur.execute("""
                    UPDATE qd_indicator_comments 
                    SET rating = ?, content = ?, updated_at = NOW()
                    WHERE id = ?
                """, (rating, content, comment_id))
                
                # 如果评分变了，更新指标的平均评分
                if old_rating != rating:
                    cur.execute("""
                        UPDATE qd_indicator_codes 
                        SET avg_rating = (
                            SELECT AVG(rating) FROM qd_indicator_comments 
                            WHERE indicator_id = ? AND parent_id IS NULL AND is_deleted = 0
                        )
                        WHERE id = ?
                    """, (indicator_id, indicator_id))
                
                db.commit()
                cur.close()
                
                logger.info(f"User {user_id} updated comment {comment_id}")
                return True, 'success', {'comment_id': comment_id}
                
        except Exception as e:
            logger.error(f"update_comment failed: {e}")
            return False, f'error: {str(e)}', {}
    
    def get_user_comment(self, user_id: int, indicator_id: int) -> Optional[Dict[str, Any]]:
        """获取用户对某个指标的评论"""
        try:
            with get_db_connection() as db:
                cur = db.cursor()
                cur.execute("""
                    SELECT id, rating, content, created_at, updated_at
                    FROM qd_indicator_comments
                    WHERE user_id = ? AND indicator_id = ? AND parent_id IS NULL AND is_deleted = 0
                """, (user_id, indicator_id))
                row = cur.fetchone()
                cur.close()
                
                if not row:
                    return None
                
                return {
                    'id': row['id'],
                    'rating': row['rating'],
                    'content': row['content'],
                    'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                    'updated_at': row['updated_at'].isoformat() if row['updated_at'] else None
                }
                
        except Exception as e:
            logger.error(f"get_user_comment failed: {e}")
            return None
    
    # ==========================================
    # 管理员审核功能
    # ==========================================
    
    def get_pending_indicators(
        self,
        page: int = 1,
        page_size: int = 20,
        review_status: str = 'pending'  # 'pending' / 'approved' / 'rejected' / 'all'
    ) -> Dict[str, Any]:
        """获取待审核的指标列表（管理员用）"""
        offset = (page - 1) * page_size
        
        try:
            with get_db_connection() as db:
                cur = db.cursor()
                
                # 构建查询条件
                where_clauses = ["i.publish_to_community = 1"]
                params = []
                
                if review_status and review_status != 'all':
                    where_clauses.append("i.review_status = ?")
                    params.append(review_status)
                
                where_sql = " AND ".join(where_clauses)
                
                # 获取总数
                count_sql = f"""
                    SELECT COUNT(*) as count 
                    FROM qd_indicator_codes i 
                    WHERE {where_sql}
                """
                cur.execute(count_sql, tuple(params))
                total = cur.fetchone()['count']
                
                # 获取列表
                query_sql = f"""
                    SELECT 
                        i.id, i.name, i.description, i.pricing_type, i.price,
                        i.preview_image, i.code, i.review_status, i.review_note, 
                        i.reviewed_at, i.reviewed_by, i.created_at,
                        u.id as author_id, u.username as author_username, 
                        u.nickname as author_nickname, u.avatar as author_avatar,
                        r.username as reviewer_username
                    FROM qd_indicator_codes i
                    LEFT JOIN qd_users u ON i.user_id = u.id
                    LEFT JOIN qd_users r ON i.reviewed_by = r.id
                    WHERE {where_sql}
                    ORDER BY i.created_at DESC
                    LIMIT ? OFFSET ?
                """
                cur.execute(query_sql, tuple(params + [page_size, offset]))
                rows = cur.fetchall() or []
                cur.close()
                
                items = []
                for row in rows:
                    items.append({
                        'id': row['id'],
                        'name': row['name'],
                        'description': row['description'][:300] if row['description'] else '',
                        'pricing_type': row['pricing_type'] or 'free',
                        'price': float(row['price'] or 0),
                        'preview_image': row['preview_image'] or '',
                        'code': row['code'] or '',  # 管理员可以看代码
                        'review_status': row['review_status'] or 'pending',
                        'review_note': row['review_note'] or '',
                        'reviewed_at': row['reviewed_at'].isoformat() if row['reviewed_at'] else None,
                        'reviewer_username': row['reviewer_username'],
                        'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                        'author': {
                            'id': row['author_id'],
                            'username': row['author_username'],
                            'nickname': row['author_nickname'] or row['author_username'],
                            'avatar': row['author_avatar'] or '/avatar2.jpg'
                        }
                    })
                
                return {
                    'items': items,
                    'total': total,
                    'page': page,
                    'page_size': page_size,
                    'total_pages': (total + page_size - 1) // page_size if total > 0 else 0
                }
                
        except Exception as e:
            logger.error(f"get_pending_indicators failed: {e}")
            return {'items': [], 'total': 0, 'page': 1, 'page_size': page_size, 'total_pages': 0}
    
    def review_indicator(
        self,
        admin_id: int,
        indicator_id: int,
        action: str,  # 'approve' / 'reject'
        note: str = ''
    ) -> Tuple[bool, str]:
        """审核指标"""
        try:
            new_status = 'approved' if action == 'approve' else 'rejected'
            note = (note or '').strip()[:500]
            
            with get_db_connection() as db:
                cur = db.cursor()
                
                # 检查指标是否存在且已发布到社区
                cur.execute("""
                    SELECT id, name, user_id FROM qd_indicator_codes 
                    WHERE id = ? AND publish_to_community = 1
                """, (indicator_id,))
                indicator = cur.fetchone()
                
                if not indicator:
                    cur.close()
                    return False, 'indicator_not_found'
                
                # 更新审核状态
                cur.execute("""
                    UPDATE qd_indicator_codes 
                    SET review_status = ?, review_note = ?, reviewed_at = NOW(), reviewed_by = ?
                    WHERE id = ?
                """, (new_status, note, admin_id, indicator_id))
                
                db.commit()
                cur.close()
                
                logger.info(f"Admin {admin_id} {action}d indicator {indicator_id}")
                return True, 'success'
                
        except Exception as e:
            logger.error(f"review_indicator failed: {e}")
            return False, f'error: {str(e)}'
    
    def unpublish_indicator(self, admin_id: int, indicator_id: int, note: str = '') -> Tuple[bool, str]:
        """下架指标（取消发布）"""
        try:
            note = (note or '').strip()[:500]
            
            with get_db_connection() as db:
                cur = db.cursor()
                
                # 检查指标是否存在
                cur.execute("""
                    SELECT id, name FROM qd_indicator_codes WHERE id = ?
                """, (indicator_id,))
                indicator = cur.fetchone()
                
                if not indicator:
                    cur.close()
                    return False, 'indicator_not_found'
                
                # 下架（取消发布）
                cur.execute("""
                    UPDATE qd_indicator_codes 
                    SET publish_to_community = 0, review_status = 'rejected', 
                        review_note = ?, reviewed_at = NOW(), reviewed_by = ?
                    WHERE id = ?
                """, (f"下架: {note}" if note else "管理员下架", admin_id, indicator_id))
                
                db.commit()
                cur.close()
                
                logger.info(f"Admin {admin_id} unpublished indicator {indicator_id}")
                return True, 'success'
                
        except Exception as e:
            logger.error(f"unpublish_indicator failed: {e}")
            return False, f'error: {str(e)}'
    
    def admin_delete_indicator(self, admin_id: int, indicator_id: int) -> Tuple[bool, str]:
        """管理员删除指标"""
        try:
            with get_db_connection() as db:
                cur = db.cursor()
                
                # 检查指标是否存在
                cur.execute("SELECT id, name FROM qd_indicator_codes WHERE id = ?", (indicator_id,))
                indicator = cur.fetchone()
                
                if not indicator:
                    cur.close()
                    return False, 'indicator_not_found'
                
                # 删除关联的评论
                cur.execute("DELETE FROM qd_indicator_comments WHERE indicator_id = ?", (indicator_id,))
                
                # 删除关联的购买记录
                cur.execute("DELETE FROM qd_indicator_purchases WHERE indicator_id = ?", (indicator_id,))
                
                # 删除指标
                cur.execute("DELETE FROM qd_indicator_codes WHERE id = ?", (indicator_id,))
                
                db.commit()
                cur.close()
                
                logger.info(f"Admin {admin_id} deleted indicator {indicator_id}")
                return True, 'success'
                
        except Exception as e:
            logger.error(f"admin_delete_indicator failed: {e}")
            return False, f'error: {str(e)}'
    
    def get_review_stats(self) -> Dict[str, int]:
        """获取审核统计"""
        try:
            with get_db_connection() as db:
                cur = db.cursor()
                cur.execute("""
                    SELECT 
                        COUNT(*) FILTER (WHERE review_status = 'pending' OR review_status IS NULL) as pending_count,
                        COUNT(*) FILTER (WHERE review_status = 'approved') as approved_count,
                        COUNT(*) FILTER (WHERE review_status = 'rejected') as rejected_count
                    FROM qd_indicator_codes
                    WHERE publish_to_community = 1
                """)
                row = cur.fetchone()
                cur.close()
                
                return {
                    'pending': row['pending_count'] or 0,
                    'approved': row['approved_count'] or 0,
                    'rejected': row['rejected_count'] or 0
                }
        except Exception as e:
            logger.error(f"get_review_stats failed: {e}")
            return {'pending': 0, 'approved': 0, 'rejected': 0}
    
    # ==========================================
    # 实盘表现（聚合回测 + 实盘交易数据）
    # ==========================================

    def get_indicator_performance(self, indicator_id: int) -> Dict[str, Any]:
        """
        获取指标的实盘表现统计

        数据来源：
        1. qd_backtest_runs - 回测记录（result_json 内含 totalReturn / winRate 等）
        2. qd_strategy_trades + qd_strategies_trading - 真实实盘交易记录
        """
        default_result = {
            'strategy_count': 0,
            'trade_count': 0,
            'win_rate': 0,
            'total_profit': 0,
            'avg_return': 0,
            'max_drawdown': 0
        }

        try:
            with get_db_connection() as db:
                cur = db.cursor()

                # ---------- Part 1: 回测数据（从 result_json 解析） ----------
                bt_returns = []
                bt_win_rates = []
                bt_drawdowns = []
                bt_trade_counts = []

                try:
                    cur.execute("""
                        SELECT result_json
                        FROM qd_backtest_runs
                        WHERE indicator_id = %s AND status = 'success'
                              AND result_json IS NOT NULL AND result_json != ''
                    """, (indicator_id,))
                    rows = cur.fetchall()

                    for row in rows:
                        try:
                            rj = json.loads(row['result_json']) if isinstance(row['result_json'], str) else {}
                            tr = float(rj.get('totalReturn', 0) or 0)
                            wr = float(rj.get('winRate', 0) or 0)
                            md = float(rj.get('maxDrawdown', 0) or 0)
                            tc = int(rj.get('totalTrades', 0) or 0)
                            bt_returns.append(tr)
                            bt_win_rates.append(wr)
                            bt_drawdowns.append(md)
                            bt_trade_counts.append(tc)
                        except (json.JSONDecodeError, TypeError, ValueError):
                            continue
                except Exception:
                    logger.debug("Backtest runs query skipped or failed", exc_info=True)

                bt_run_count = len(bt_returns)

                # ---------- Part 2: 实盘交易数据 ----------
                live_strategy_count = 0
                live_trade_count = 0
                live_win_rate = 0.0
                live_total_profit = 0.0

                try:
                    # 找出使用该指标的策略（indicator_config JSON 中 indicator_id 匹配）
                    cur.execute("""
                        SELECT id FROM qd_strategies_trading
                        WHERE indicator_config::text LIKE %s
                    """, (f'%"indicator_id": {indicator_id}%',))
                    strategy_rows = cur.fetchall()

                    # 也尝试匹配无空格的格式
                    if not strategy_rows:
                        cur.execute("""
                            SELECT id FROM qd_strategies_trading
                            WHERE indicator_config::text LIKE %s
                        """, (f'%"indicator_id":{indicator_id}%',))
                        strategy_rows = cur.fetchall()

                    if strategy_rows:
                        strategy_ids = [r['id'] for r in strategy_rows]
                        live_strategy_count = len(strategy_ids)

                        placeholders = ','.join(['%s'] * len(strategy_ids))
                        cur.execute(f"""
                            SELECT 
                                COUNT(*) as trade_count,
                                SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) as win_count,
                                SUM(profit) as total_profit
                            FROM qd_strategy_trades
                            WHERE strategy_id IN ({placeholders})
                              AND profit != 0
                        """, tuple(strategy_ids))
                        trade_row = cur.fetchone()

                        if trade_row and (trade_row['trade_count'] or 0) > 0:
                            live_trade_count = int(trade_row['trade_count'] or 0)
                            win_count = int(trade_row['win_count'] or 0)
                            live_win_rate = round(win_count / live_trade_count * 100, 2) if live_trade_count > 0 else 0.0
                            live_total_profit = round(float(trade_row['total_profit'] or 0), 2)
                except Exception:
                    logger.debug("Live trading query skipped or failed", exc_info=True)

                cur.close()

                # ---------- Combine results ----------
                total_strategy_count = bt_run_count + live_strategy_count
                total_trade_count = sum(bt_trade_counts) + live_trade_count

                # 综合胜率：优先实盘 > 回测平均
                if live_trade_count > 0:
                    combined_win_rate = live_win_rate
                elif bt_win_rates:
                    combined_win_rate = round(sum(bt_win_rates) / len(bt_win_rates), 2)
                else:
                    combined_win_rate = 0.0

                # 平均收益率（回测 totalReturn %）
                avg_return = round(sum(bt_returns) / len(bt_returns), 2) if bt_returns else 0.0

                # 总利润：优先用实盘绝对利润，无实盘则显示回测平均收益率
                combined_profit = live_total_profit if live_trade_count > 0 else avg_return

                # 最大回撤取回测中最差的（maxDrawdown 是负数，取最小即最差）
                avg_drawdown = round(min(bt_drawdowns), 2) if bt_drawdowns else 0.0

                if total_strategy_count == 0 and total_trade_count == 0:
                    return default_result

                return {
                    'strategy_count': total_strategy_count,
                    'trade_count': total_trade_count,
                    'win_rate': combined_win_rate,
                    'total_profit': round(combined_profit, 2),
                    'avg_return': avg_return,
                    'max_drawdown': avg_drawdown
                }

        except Exception as e:
            logger.error(f"get_indicator_performance failed: {e}")
            return default_result


# 全局单例
_community_service = None


def get_community_service() -> CommunityService:
    """获取社区服务单例"""
    global _community_service
    if _community_service is None:
        _community_service = CommunityService()
    return _community_service
