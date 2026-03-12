"""
USDT Payment Service (方案B：每单独立地址 + 自动对账)

MVP:
- 只支持 USDT-TRC20
- 使用 XPUB 派生地址（服务端只保存 xpub，不保存私钥）
- 后台 Worker 线程自动轮询链上到账 + 前端轮询双保险
"""

import os
import threading
import time
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import requests

from app.utils.db import get_db_connection
from app.utils.logger import get_logger
from app.services.billing_service import get_billing_service

logger = get_logger(__name__)


class UsdtPaymentService:
    def __init__(self):
        self.billing = get_billing_service()

    # -------------------- Config --------------------

    def _get_cfg(self) -> Dict[str, Any]:
        return {
            "enabled": str(os.getenv("USDT_PAY_ENABLED", "False")).lower() in ("1", "true", "yes"),
            "chain": (os.getenv("USDT_PAY_CHAIN", "TRC20") or "TRC20").upper(),
            "xpub_trc20": (os.getenv("USDT_TRC20_XPUB", "") or "").strip(),
            "trongrid_base": (os.getenv("TRONGRID_BASE_URL", "https://api.trongrid.io") or "").strip().rstrip("/"),
            "trongrid_key": (os.getenv("TRONGRID_API_KEY", "") or "").strip(),
            "usdt_trc20_contract": (os.getenv("USDT_TRC20_CONTRACT", "TXLAQ63Xg1NAzckPwKHvzw7CSEmLMEqcdj") or "").strip(),
            "confirm_seconds": int(float(os.getenv("USDT_PAY_CONFIRM_SECONDS", "30") or 30)),
            "order_expire_minutes": int(float(os.getenv("USDT_PAY_EXPIRE_MINUTES", "30") or 30)),
        }

    # -------------------- Schema --------------------

    def _ensure_schema_best_effort(self, cur):
        """Best-effort create table/columns for old databases."""
        try:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS qd_usdt_orders (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES qd_users(id) ON DELETE CASCADE,
                    plan VARCHAR(20) NOT NULL,
                    chain VARCHAR(20) NOT NULL DEFAULT 'TRC20',
                    amount_usdt DECIMAL(20,6) NOT NULL DEFAULT 0,
                    address_index INTEGER NOT NULL DEFAULT 0,
                    address VARCHAR(80) NOT NULL DEFAULT '',
                    status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    tx_hash VARCHAR(120) DEFAULT '',
                    paid_at TIMESTAMP,
                    confirmed_at TIMESTAMP,
                    expires_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
                """
            )
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_usdt_orders_address_unique ON qd_usdt_orders(chain, address)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_usdt_orders_user_id ON qd_usdt_orders(user_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_usdt_orders_status ON qd_usdt_orders(status)")
        except Exception:
            pass

    # -------------------- Address derivation --------------------

    def _derive_trc20_address_from_xpub(self, xpub: str, index: int) -> str:
        """
        Derive TRON address from xpub.

        Requires bip_utils.
        NOTE:
        - Some wallets export account-level xpub at m/44'/195'/0' (level=3).
        - Some export change-level xpub at m/44'/195'/0'/0 (level=4, external chain).
        This function supports both by normalizing to change-level before AddressIndex().
        """
        try:
            from bip_utils import Bip44, Bip44Coins, Bip44Changes
        except Exception as e:
            raise RuntimeError(f"bip_utils_missing:{e}")

        if not xpub:
            raise RuntimeError("missing_xpub")
        if index < 0:
            raise RuntimeError("invalid_index")

        ctx = Bip44.FromExtendedKey(xpub, Bip44Coins.TRON)
        lvl = int(ctx.Level())
        # Normalize to change-level (external chain) so we can derive addresses by index
        if lvl == 3:
            # account-level xpub: m/44'/195'/0'
            ctx = ctx.Change(Bip44Changes.CHAIN_EXT)
        elif lvl == 4:
            # change-level xpub: m/44'/195'/0'/0
            pass
        elif lvl == 5:
            # address-level xpub: cannot derive other indexes
            if index != 0:
                raise RuntimeError("xpub_is_address_level")
            return ctx.PublicKey().ToAddress()
        else:
            raise RuntimeError(f"unsupported_xpub_level:{lvl}")

        addr = ctx.AddressIndex(index).PublicKey().ToAddress()
        return addr

    # -------------------- Orders --------------------

    def create_order(self, user_id: int, plan: str) -> Tuple[bool, str, Dict[str, Any]]:
        cfg = self._get_cfg()
        if not cfg["enabled"]:
            return False, "usdt_pay_disabled", {}
        if cfg["chain"] != "TRC20":
            return False, "unsupported_chain", {}
        plan = (plan or "").strip().lower()
        if plan not in ("monthly", "yearly", "lifetime"):
            return False, "invalid_plan", {}

        plans = self.billing.get_membership_plans()
        amount = Decimal(str(plans.get(plan, {}).get("price_usd") or 0))
        if amount <= 0:
            return False, "invalid_amount", {}

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=cfg["order_expire_minutes"])

        try:
            with get_db_connection() as db:
                cur = db.cursor()
                self._ensure_schema_best_effort(cur)

                # allocate next address index (simple monotonic)
                cur.execute(
                    "SELECT COALESCE(MAX(address_index), -1) as max_idx FROM qd_usdt_orders WHERE chain = 'TRC20'"
                )
                max_idx = cur.fetchone().get("max_idx")
                next_idx = int(max_idx) + 1

                address = self._derive_trc20_address_from_xpub(cfg["xpub_trc20"], next_idx)

                cur.execute(
                    """
                    INSERT INTO qd_usdt_orders
                      (user_id, plan, chain, amount_usdt, address_index, address, status, expires_at, created_at, updated_at)
                    VALUES (?, ?, 'TRC20', ?, ?, ?, 'pending', ?, NOW(), NOW())
                    RETURNING id
                    """,
                    (user_id, plan, float(amount), next_idx, address, expires_at),
                )
                row = cur.fetchone() or {}
                order_id = row.get("id")
                db.commit()
                cur.close()

            return True, "success", {
                "order_id": order_id,
                "plan": plan,
                "chain": "TRC20",
                "amount_usdt": str(amount),
                "address": address,
                "expires_at": expires_at.isoformat(),
            }
        except Exception as e:
            logger.error(f"create_order failed: {e}", exc_info=True)
            return False, f"error:{str(e)}", {}

    def get_order(self, user_id: int, order_id: int, refresh: bool = True) -> Tuple[bool, str, Dict[str, Any]]:
        try:
            with get_db_connection() as db:
                cur = db.cursor()
                self._ensure_schema_best_effort(cur)

                cur.execute(
                    """
                    SELECT id, user_id, plan, chain, amount_usdt, address_index, address, status, tx_hash,
                           paid_at, confirmed_at, expires_at, created_at, updated_at
                    FROM qd_usdt_orders
                    WHERE id = ? AND user_id = ?
                    """,
                    (order_id, user_id),
                )
                row = cur.fetchone()
                if not row:
                    cur.close()
                    return False, "order_not_found", {}

                if refresh:
                    self._refresh_order_in_tx(cur, row)
                    db.commit()
                    # re-read
                    cur.execute(
                        """
                        SELECT id, user_id, plan, chain, amount_usdt, address_index, address, status, tx_hash,
                               paid_at, confirmed_at, expires_at, created_at, updated_at
                        FROM qd_usdt_orders
                        WHERE id = ? AND user_id = ?
                        """,
                        (order_id, user_id),
                    )
                    row = cur.fetchone()

                cur.close()

            return True, "success", self._row_to_dict(row)
        except Exception as e:
            logger.error(f"get_order failed: {e}", exc_info=True)
            return False, f"error:{str(e)}", {}

    def _row_to_dict(self, row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "order_id": row.get("id"),
            "plan": row.get("plan"),
            "chain": row.get("chain"),
            "amount_usdt": str(row.get("amount_usdt") or 0),
            "address": row.get("address") or "",
            "status": row.get("status") or "",
            "tx_hash": row.get("tx_hash") or "",
            "paid_at": row.get("paid_at").isoformat() if row.get("paid_at") else None,
            "confirmed_at": row.get("confirmed_at").isoformat() if row.get("confirmed_at") else None,
            "expires_at": row.get("expires_at").isoformat() if row.get("expires_at") else None,
            "created_at": row.get("created_at").isoformat() if row.get("created_at") else None,
        }

    # -------------------- Chain check --------------------

    def _refresh_order_in_tx(self, cur, row: Dict[str, Any]) -> None:
        """Check chain status for a single order and update in the current transaction."""
        cfg = self._get_cfg()
        status = (row.get("status") or "").lower()
        chain = (row.get("chain") or "").upper()
        order_id = row.get("id")

        # --- Expiry check (only for pending; paid orders should still be confirmed) ---
        expires_at = row.get("expires_at")
        now = datetime.now(timezone.utc)
        if expires_at and isinstance(expires_at, datetime):
            exp = expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if status == "pending" and exp <= now:
                cur.execute("UPDATE qd_usdt_orders SET status = 'expired', updated_at = NOW() WHERE id = ?", (order_id,))
                return

        if chain != "TRC20":
            return
        if status not in ("pending", "paid"):
            return

        address = row.get("address") or ""
        amount = Decimal(str(row.get("amount_usdt") or 0))
        if not address or amount <= 0:
            return

        # --- For 'paid' status, skip chain query and just check confirm delay ---
        if status == "paid":
            self._try_confirm_paid_order(cur, row, cfg, now)
            return

        # --- For 'pending' status, query chain for incoming transfer ---
        tx = self._find_trc20_usdt_incoming(address, amount, row.get("created_at"))
        if not tx:
            return

        tx_hash = tx.get("transaction_id") or ""
        paid_at = datetime.now(timezone.utc)
        cur.execute(
            "UPDATE qd_usdt_orders SET status = 'paid', tx_hash = ?, paid_at = ?, updated_at = NOW() WHERE id = ? AND status = 'pending'",
            (tx_hash, paid_at, order_id),
        )

        # Try to confirm immediately if delay is satisfied
        confirm_sec = int(cfg.get("confirm_seconds") or 30)
        try:
            tx_ts = tx.get("block_timestamp")
            if tx_ts:
                tx_time = datetime.fromtimestamp(int(tx_ts) / 1000.0, tz=timezone.utc)
                if (now - tx_time).total_seconds() >= confirm_sec:
                    self._confirm_and_activate_in_tx(cur, order_id, row.get("user_id"), row.get("plan"), tx_hash)
            elif confirm_sec <= 0:
                self._confirm_and_activate_in_tx(cur, order_id, row.get("user_id"), row.get("plan"), tx_hash)
        except Exception:
            pass

    def _try_confirm_paid_order(self, cur, row: Dict[str, Any], cfg: Dict[str, Any], now: datetime) -> None:
        """For orders already in 'paid' status, check if confirm delay is met and activate."""
        confirm_sec = int(cfg.get("confirm_seconds") or 30)
        paid_at = row.get("paid_at")
        if paid_at:
            if isinstance(paid_at, str):
                try:
                    paid_at = datetime.fromisoformat(paid_at.replace("Z", "+00:00"))
                except Exception:
                    paid_at = None
            if paid_at and paid_at.tzinfo is None:
                paid_at = paid_at.replace(tzinfo=timezone.utc)
            if paid_at and (now - paid_at).total_seconds() >= confirm_sec:
                self._confirm_and_activate_in_tx(cur, row["id"], row.get("user_id"), row.get("plan"), row.get("tx_hash") or "")
                return
        # Fallback: if paid_at missing but confirm_sec <= 0, confirm now
        if confirm_sec <= 0:
            self._confirm_and_activate_in_tx(cur, row["id"], row.get("user_id"), row.get("plan"), row.get("tx_hash") or "")

    def _confirm_and_activate_in_tx(self, cur, order_id: int, user_id: int, plan: str, tx_hash: str) -> None:
        """Mark order as confirmed and activate membership. Idempotent: skips if already confirmed."""
        # --- Idempotency check: re-read current status ---
        try:
            cur.execute("SELECT status FROM qd_usdt_orders WHERE id = ?", (order_id,))
            current = cur.fetchone()
            if current and (current.get("status") or "").lower() == "confirmed":
                logger.debug(f"USDT order {order_id} already confirmed, skipping activation.")
                return
        except Exception:
            pass

        # Mark confirmed
        cur.execute(
            "UPDATE qd_usdt_orders SET status='confirmed', confirmed_at = NOW(), updated_at = NOW() WHERE id = ? AND status IN ('paid','pending')",
            (order_id,),
        )
        # Activate membership
        try:
            ok, msg, data = self.billing.purchase_membership(int(user_id), str(plan))
            logger.info(f"USDT activate membership: order={order_id} user={user_id} plan={plan} ok={ok} msg={msg}")
        except Exception as e:
            logger.error(f"USDT activate membership failed: order={order_id} err={e}", exc_info=True)

    def _find_trc20_usdt_incoming(self, address: str, amount_usdt: Decimal, created_at: Optional[datetime]) -> Optional[Dict[str, Any]]:
        cfg = self._get_cfg()
        base = cfg["trongrid_base"]
        contract = cfg["usdt_trc20_contract"]

        url = f"{base}/v1/accounts/{address}/transactions/trc20"
        headers = {}
        if cfg["trongrid_key"]:
            headers["TRON-PRO-API-KEY"] = cfg["trongrid_key"]

        params = {
            "only_to": "true",
            "limit": 50,
            "contract_address": contract,
        }

        try:
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            if resp.status_code != 200:
                return None
            data = resp.json() or {}
            items = data.get("data") or []
            # TRC20 USDT has 6 decimals
            target = int((amount_usdt * Decimal("1000000")).to_integral_value())

            min_ts = None
            if created_at and isinstance(created_at, datetime):
                ct = created_at
                if ct.tzinfo is None:
                    ct = ct.replace(tzinfo=timezone.utc)
                min_ts = int(ct.timestamp() * 1000) - 60_000

            for it in items:
                try:
                    if it.get("to") != address:
                        continue
                    if min_ts and int(it.get("block_timestamp") or 0) < min_ts:
                        continue
                    val = int(it.get("value") or 0)
                    # Accept payments >= order amount (tolerance for overpayment)
                    if val < target:
                        continue
                    return it
                except Exception:
                    continue
        except Exception:
            return None
        return None

    # -------------------- Batch refresh (for worker) --------------------

    def refresh_all_active_orders(self) -> int:
        """
        Scan all pending/paid USDT orders and refresh their chain status.
        Called by the background UsdtOrderWorker.

        Returns the number of orders that were updated to 'confirmed' or 'expired'.
        """
        updated = 0
        try:
            with get_db_connection() as db:
                cur = db.cursor()
                self._ensure_schema_best_effort(cur)

                cur.execute(
                    """
                    SELECT id, user_id, plan, chain, amount_usdt, address_index, address, status, tx_hash,
                           paid_at, confirmed_at, expires_at, created_at, updated_at
                    FROM qd_usdt_orders
                    WHERE status IN ('pending', 'paid')
                    ORDER BY created_at ASC
                    LIMIT 100
                    """
                )
                rows = cur.fetchall() or []

                for row in rows:
                    old_status = (row.get("status") or "").lower()
                    try:
                        self._refresh_order_in_tx(cur, row)
                    except Exception as e:
                        logger.debug(f"refresh_all: order {row.get('id')} error: {e}")
                        continue

                    # Check if status changed
                    try:
                        cur.execute("SELECT status FROM qd_usdt_orders WHERE id = ?", (row["id"],))
                        new_row = cur.fetchone()
                        new_status = (new_row.get("status") or "").lower() if new_row else old_status
                        if new_status != old_status:
                            updated += 1
                            logger.info(f"USDT order {row['id']}: {old_status} -> {new_status}")
                    except Exception:
                        pass

                db.commit()
                cur.close()
        except Exception as e:
            logger.error(f"refresh_all_active_orders error: {e}", exc_info=True)
        return updated


# ==================== Background Worker ====================

class UsdtOrderWorker:
    """
    Background thread that periodically scans pending/paid USDT orders
    and checks on-chain status via TronGrid API.

    This ensures that even if the user closes the browser after payment,
    the order will still be confirmed and membership activated.
    """

    def __init__(self, poll_interval_sec: float = 30.0):
        self.poll_interval_sec = float(poll_interval_sec)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def start(self) -> bool:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return True
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_loop, name="UsdtOrderWorker", daemon=True)
            self._thread.start()
            logger.info("UsdtOrderWorker started (interval=%ss)", self.poll_interval_sec)
            return True

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
            logger.info("UsdtOrderWorker stopped")

    def _run_loop(self):
        # Wait a bit on startup to let the app fully initialize
        self._stop_event.wait(timeout=10)

        while not self._stop_event.is_set():
            try:
                svc = get_usdt_payment_service()
                cfg = svc._get_cfg()
                if cfg["enabled"]:
                    updated = svc.refresh_all_active_orders()
                    if updated > 0:
                        logger.info(f"UsdtOrderWorker: refreshed {updated} orders")
            except Exception as e:
                logger.error(f"UsdtOrderWorker loop error: {e}", exc_info=True)

            self._stop_event.wait(timeout=self.poll_interval_sec)


# ==================== Singletons ====================

_svc = None
_worker = None


def get_usdt_payment_service() -> UsdtPaymentService:
    global _svc
    if _svc is None:
        _svc = UsdtPaymentService()
    return _svc


def get_usdt_order_worker() -> UsdtOrderWorker:
    global _worker
    if _worker is None:
        interval = float(os.getenv("USDT_WORKER_POLL_INTERVAL", "30"))
        _worker = UsdtOrderWorker(poll_interval_sec=interval)
    return _worker
