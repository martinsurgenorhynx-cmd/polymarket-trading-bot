"""
Strategy signal notification service.

This module implements per-strategy notification channels based on the frontend schema:

notification_config = {
  "channels": ["browser", "email", "phone", "telegram", "discord", "webhook"],
  "targets": {
    "email": "foo@example.com",
    "phone": "+15551234567",
    "telegram": "12345678 or @username",
    "discord": "https://discord.com/api/webhooks/...",
    "webhook": "https://example.com/webhook"
  }
}
"""

from __future__ import annotations

import html
import hmac
import hashlib
import json
import os
import smtplib
import time
import traceback
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any, Dict, List, Optional, Tuple

import requests

from app.utils.db import get_db_connection
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(x).strip() for x in value if str(x).strip()]
    s = str(value).strip()
    if not s:
        return []
    # Allow comma-separated inputs.
    if "," in s:
        return [x.strip() for x in s.split(",") if x.strip()]
    return [s]


def _safe_json(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            obj = json.loads(value)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}
    return {}


def _signal_meta(signal_type: str) -> Dict[str, str]:
    st = (signal_type or "").strip().lower()
    action = "signal"
    if st.startswith("open_"):
        action = "open"
    elif st.startswith("add_"):
        action = "add"
    elif st.startswith("close_"):
        action = "close"
    elif st.startswith("reduce_"):
        action = "reduce"

    side = "long" if "long" in st else ("short" if "short" in st else "")
    return {"action": action, "side": side, "type": st}


def _fmt_float(value: Any, *, max_decimals: int = 10) -> str:
    try:
        v = float(value or 0.0)
    except Exception:
        v = 0.0
    s = f"{v:.{int(max_decimals)}f}"
    s = s.rstrip("0").rstrip(".")
    return s or "0"


class SignalNotifier:
    """
    Notify signal events across channels.

    通知配置说明:
    - 用户在个人中心配置自己的通知设置（telegram_bot_token, telegram_chat_id, email 等）
    - 创建策略/监控时，系统自动使用用户配置的通知目标

    公共服务配置（管理员在系统设置中配置）:
    - SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM, SMTP_USE_TLS
      (邮件服务，所有用户共用)
    - TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER
      (短信服务，所有用户共用)

    可选的环境变量:
    - SIGNAL_NOTIFY_TIMEOUT_SEC: HTTP timeout (default: 6)
    """

    def __init__(self) -> None:
        try:
            self.timeout_sec = float(os.getenv("SIGNAL_NOTIFY_TIMEOUT_SEC") or "6")
        except Exception:
            self.timeout_sec = 6.0

        # 公共 SMTP 配置（管理员在系统设置中配置）
        self.smtp_host = (os.getenv("SMTP_HOST") or "").strip()
        try:
            self.smtp_port = int(os.getenv("SMTP_PORT") or "587")
        except Exception:
            self.smtp_port = 587
        self.smtp_user = (os.getenv("SMTP_USER") or "").strip()
        self.smtp_password = (os.getenv("SMTP_PASSWORD") or "").strip()
        self.smtp_from = (os.getenv("SMTP_FROM") or self.smtp_user or "").strip()
        self.smtp_use_tls = (os.getenv("SMTP_USE_TLS") or "true").strip().lower() == "true"
        # Some providers require implicit SSL (port 465). Support it via SMTP_USE_SSL.
        self.smtp_use_ssl = (os.getenv("SMTP_USE_SSL") or "").strip().lower() == "true"

        self.twilio_sid = (os.getenv("TWILIO_ACCOUNT_SID") or "").strip()
        self.twilio_token = (os.getenv("TWILIO_AUTH_TOKEN") or "").strip()
        self.twilio_from = (os.getenv("TWILIO_FROM_NUMBER") or "").strip()

    def notify_signal(
        self,
        *,
        strategy_id: int,
        strategy_name: str,
        symbol: str,
        signal_type: str,
        price: float = 0.0,
        stake_amount: float = 0.0,
        direction: str = "long",
        notification_config: Optional[Dict[str, Any]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        cfg = _safe_json(notification_config or {})
        channels = _as_list(cfg.get("channels"))
        if not channels:
            channels = ["browser"]

        targets = _safe_json(cfg.get("targets") or {})
        extra = extra if isinstance(extra, dict) else {}

        payload = self._build_payload(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            symbol=symbol,
            signal_type=signal_type,
            price=price,
            stake_amount=stake_amount,
            direction=direction,
            extra=extra,
        )
        rendered = self._render_messages(payload)
        title = rendered.get("title") or ""
        message_plain = rendered.get("plain") or ""

        results: Dict[str, Dict[str, Any]] = {}
        for ch in channels:
            c = (ch or "").strip().lower()
            if not c:
                continue
            try:
                if c == "browser":
                    ok, err = self._notify_browser(
                        strategy_id=strategy_id,
                        symbol=symbol,
                        signal_type=signal_type,
                        channels=channels,
                        title=title,
                        message=message_plain,
                        payload=payload,
                    )
                elif c == "webhook":
                    url = (targets.get("webhook") or "").strip()
                    ok, err = self._notify_webhook(
                        url=url,
                        payload=payload,
                        headers_override=(targets.get("webhook_headers") or targets.get("webhookHeaders") or None),
                        token_override=(targets.get("webhook_token") or targets.get("webhookToken") or None),
                        signing_secret_override=(
                            targets.get("webhook_signing_secret")
                            or targets.get("webhookSigningSecret")
                            or None
                        ),
                    )
                elif c == "discord":
                    url = (targets.get("discord") or "").strip()
                    ok, err = self._notify_discord(url=url, payload=payload, fallback_text=message_plain)
                elif c == "telegram":
                    chat_id = (targets.get("telegram") or "").strip()
                    # User's token takes priority, then falls back to env TELEGRAM_BOT_TOKEN.
                    token_override = ""
                    try:
                        token_override = str(
                            targets.get("telegram_bot_token")
                            or targets.get("telegram_token")
                            or cfg.get("telegram_bot_token")
                            or cfg.get("telegram_token")
                            or ""
                        ).strip()
                    except Exception:
                        token_override = ""
                    ok, err = self._notify_telegram(
                        chat_id=chat_id,
                        text=rendered.get("telegram_html") or message_plain,
                        token_override=token_override,
                        parse_mode="HTML",
                    )
                elif c == "email":
                    to_email = (targets.get("email") or "").strip()
                    ok, err = self._notify_email(
                        to_email=to_email,
                        subject=title,
                        body_text=message_plain,
                        body_html=rendered.get("email_html") or "",
                    )
                elif c == "phone":
                    to_phone = (targets.get("phone") or "").strip()
                    ok, err = self._notify_phone(to_phone=to_phone, body=message_plain)
                else:
                    ok, err = False, f"unsupported_channel:{c}"
            except Exception as e:
                ok, err = False, str(e)

            results[c] = {"ok": bool(ok), "error": (err or "")}
            if not ok and c in ("webhook", "discord"):
                # Keep logs high-signal and avoid leaking full URLs (webhook URLs contain secrets).
                logger.info(
                    f"notify failed: channel={c} strategy_id={strategy_id} symbol={symbol} signal={signal_type} err={err}"
                )

        return results

    def _build_payload(
        self,
        *,
        strategy_id: int,
        strategy_name: str,
        symbol: str,
        signal_type: str,
        price: float,
        stake_amount: float,
        direction: str,
        extra: Dict[str, Any],
    ) -> Dict[str, Any]:
        now = int(time.time())
        iso = datetime.fromtimestamp(now, tz=timezone.utc).isoformat()
        meta = _signal_meta(signal_type)

        pending_id = None
        try:
            pending_id = int((extra or {}).get("pending_order_id") or 0) or None
        except Exception:
            pending_id = None

        return {
            "event": "qd.signal",
            "version": 1,
            "timestamp": now,
            "timestamp_iso": iso,
            "strategy": {
                "id": int(strategy_id),
                "name": str(strategy_name or ""),
            },
            "instrument": {
                "symbol": str(symbol or ""),
            },
            "signal": {
                "type": meta.get("type") or str(signal_type or ""),
                "action": meta.get("action") or "signal",
                "side": meta.get("side") or "",
                "direction": str(direction or ""),
            },
            "order": {
                "ref_price": float(price or 0.0),
                "stake_amount": float(stake_amount or 0.0),
            },
            "trace": {
                "pending_order_id": pending_id,
                "mode": str((extra or {}).get("mode") or ""),
            },
            "extra": extra or {},
        }

    def _render_messages(self, payload: Dict[str, Any]) -> Dict[str, str]:
        strategy = (payload or {}).get("strategy") or {}
        instrument = (payload or {}).get("instrument") or {}
        sig = (payload or {}).get("signal") or {}
        order = (payload or {}).get("order") or {}
        trace = (payload or {}).get("trace") or {}

        symbol = str(instrument.get("symbol") or "")
        stype = str(sig.get("type") or "")
        action = str(sig.get("action") or "").upper()
        side = str(sig.get("side") or "").upper()
        title = f"QD Signal | {symbol} | {action} {side}".strip()

        price_s = _fmt_float(order.get("ref_price") or 0.0, max_decimals=10)
        stake_s = _fmt_float(order.get("stake_amount") or 0.0, max_decimals=12)
        pending_id = int(trace.get("pending_order_id") or 0) if trace.get("pending_order_id") else 0
        mode = str(trace.get("mode") or "")
        ts_iso = str(payload.get("timestamp_iso") or "")

        plain_lines = [
            "QuantDinger Signal",
            f"Strategy: {strategy.get('name') or ''} (#{int(strategy.get('id') or 0)})",
            f"Symbol: {symbol}",
            f"Signal: {stype}",
            f"Price: {price_s}",
            f"Stake: {stake_s}",
        ]
        if pending_id:
            plain_lines.append(f"PendingOrder: {pending_id}")
        if mode:
            plain_lines.append(f"Mode: {mode}")
        if ts_iso:
            plain_lines.append(f"Time(UTC): {ts_iso}")

        # Telegram (HTML) message. Escape all dynamic values.
        t_strategy = f"{strategy.get('name') or ''} (#{int(strategy.get('id') or 0)})"
        telegram_lines = [
            "<b>QuantDinger Signal</b>",
            "",
            f"<b>Strategy</b>: <code>{html.escape(str(t_strategy))}</code>",
            f"<b>Symbol</b>: <code>{html.escape(symbol)}</code>",
            f"<b>Signal</b>: <code>{html.escape(stype)}</code>",
            f"<b>Price</b>: <code>{html.escape(price_s)}</code>",
            f"<b>Stake</b>: <code>{html.escape(stake_s)}</code>",
        ]
        if pending_id:
            telegram_lines.append(f"<b>PendingOrder</b>: <code>{pending_id}</code>")
        if mode:
            telegram_lines.append(f"<b>Mode</b>: <code>{html.escape(mode)}</code>")
        if ts_iso:
            telegram_lines.append(f"<b>Time (UTC)</b>: <code>{html.escape(ts_iso)}</code>")
        telegram_html = "\n".join([x for x in telegram_lines if x is not None])

        # Email (HTML) message. Keep inline CSS for maximum compatibility.
        email_html = self._build_email_html(
            title_text="QuantDinger Signal",
            strategy_text=t_strategy,
            symbol=symbol,
            signal_type=stype,
            price_text=price_s,
            stake_text=stake_s,
            pending_id=pending_id or None,
            mode_text=mode or "",
            timestamp_iso=ts_iso or "",
        )

        return {
            "title": title,
            "plain": "\n".join(plain_lines),
            "telegram_html": telegram_html,
            "email_html": email_html,
        }

    def _build_email_html(
        self,
        *,
        title_text: str,
        strategy_text: str,
        symbol: str,
        signal_type: str,
        price_text: str,
        stake_text: str,
        pending_id: Optional[int],
        mode_text: str,
        timestamp_iso: str,
    ) -> str:
        def esc(s: Any) -> str:
            return html.escape(str(s or ""))

        rows: List[Tuple[str, str]] = [
            ("Strategy", strategy_text),
            ("Symbol", symbol),
            ("Signal", signal_type),
            ("Price", price_text),
            ("Stake", stake_text),
        ]
        if pending_id:
            rows.append(("PendingOrder", str(int(pending_id))))
        if mode_text:
            rows.append(("Mode", mode_text))
        if timestamp_iso:
            rows.append(("Time (UTC)", timestamp_iso))

        tr_html = "\n".join(
            [
                (
                    "<tr>"
                    "<td style='padding:10px 12px;border-top:1px solid #eaecef;color:#57606a;width:160px;'>"
                    f"{esc(k)}"
                    "</td>"
                    "<td style='padding:10px 12px;border-top:1px solid #eaecef;color:#24292f;font-family:ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, \"Liberation Mono\", \"Courier New\", monospace;'>"
                    f"{esc(v)}"
                    "</td>"
                    "</tr>"
                )
                for (k, v) in rows
            ]
        )

        return f"""\
<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#f6f8fa;">
    <div style="max-width:640px;margin:0 auto;padding:24px;">
      <div style="background:#111827;color:#ffffff;padding:16px 18px;border-radius:12px 12px 0 0;">
        <div style="font-size:16px;letter-spacing:0.2px;font-weight:600;">{esc(title_text)}</div>
        <div style="margin-top:6px;font-size:12px;color:#d1d5db;">{esc(timestamp_iso) if timestamp_iso else ""}</div>
      </div>
      <div style="background:#ffffff;border:1px solid #eaecef;border-top:0;border-radius:0 0 12px 12px;overflow:hidden;">
        <table cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse;">
          {tr_html}
        </table>
        <div style="padding:14px 16px;color:#6e7781;font-size:12px;border-top:1px solid #eaecef;">
          Generated by QuantDinger
        </div>
      </div>
    </div>
  </body>
</html>
"""

    def _notify_browser(
        self,
        *,
        strategy_id: int,
        symbol: str,
        signal_type: str,
        channels: List[str],
        title: str,
        message: str,
        payload: Dict[str, Any],
        user_id: int = None,
    ) -> Tuple[bool, str]:
        try:
            now = int(time.time())
            # Get user_id from strategy if not provided
            if user_id is None:
                try:
                    with get_db_connection() as db:
                        cur = db.cursor()
                        cur.execute("SELECT user_id FROM qd_strategies_trading WHERE id = ?", (strategy_id,))
                        row = cur.fetchone()
                        cur.close()
                    user_id = int((row or {}).get('user_id') or 1)
                except Exception:
                    user_id = 1
            with get_db_connection() as db:
                cur = db.cursor()
                cur.execute(
                    """
                    INSERT INTO qd_strategy_notifications
                    (user_id, strategy_id, symbol, signal_type, channels, title, message, payload_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, NOW())
                    """,
                    (
                        int(user_id),
                        int(strategy_id),
                        str(symbol or ""),
                        str(signal_type or ""),
                        ",".join([str(c) for c in (channels or [])]),
                        str(title or ""),
                        str(message or ""),
                        json.dumps(payload or {}, ensure_ascii=False),
                    ),
                )
                db.commit()
                cur.close()
            return True, ""
        except Exception as e:
            logger.warning(f"browser notify persist failed: {e}")
            logger.error('browser.error', traceback=traceback.format_exc())
            return False, str(e)

    def _notify_webhook(
        self,
        *,
        url: str,
        payload: Dict[str, Any],
        headers_override: Any = None,
        token_override: Any = None,
        signing_secret_override: Any = None,
    ) -> Tuple[bool, str]:
        """
        Generic webhook delivery.

        用户在个人中心配置：
        - webhook_url: Webhook 地址
        - webhook_token: Bearer Token（可选）

        支持功能：
        - 自定义 headers: notification_config.targets.webhook_headers
        - Bearer Token: notification_config.targets.webhook_token
        - 签名验证: notification_config.targets.webhook_signing_secret
        - 自动重试: 429/5xx 时重试一次
        """
        if not url:
            return False, "missing_webhook_url"
        if not (str(url).startswith("http://") or str(url).startswith("https://")):
            return False, "invalid_webhook_url"

        headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "User-Agent": "QuantDinger/1.0 (+https://www.quantdinger.com)",
        }

        # Per-strategy header overrides (optional)
        wh = headers_override
        if isinstance(wh, str) and wh.strip():
            try:
                obj = json.loads(wh)
                wh = obj if isinstance(obj, dict) else None
            except Exception:
                wh = None
        if isinstance(wh, dict):
            for k, v in wh.items():
                kk = str(k or "").strip()
                if not kk:
                    continue
                headers[kk] = str(v if v is not None else "")

        # Auth (user's token from notification_config.targets.webhook_token)
        tok = str(token_override or "").strip()
        if tok and "Authorization" not in headers:
            headers["Authorization"] = f"Bearer {tok}"

        # Optional signing secret (per-strategy override, else env)
        signing_secret = str(signing_secret_override or "").strip() or (os.getenv("SIGNAL_WEBHOOK_SIGNING_SECRET") or "").strip()
        if signing_secret:
            try:
                ts = str(int(time.time()))
                body = json.dumps(payload or {}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                sig_base = (ts + ".").encode("utf-8") + body
                sig = hmac.new(signing_secret.encode("utf-8"), sig_base, hashlib.sha256).hexdigest()
                headers["X-QD-Timestamp"] = ts
                headers["X-QD-Signature"] = sig
                # Send raw bytes so signature matches what we sign.
                def _post_once(timeout: float) -> requests.Response:
                    return requests.post(url, data=body, headers=headers, timeout=timeout)
            except Exception as e:
                return False, f"webhook_signing_failed:{e}"
        else:
            def _post_once(timeout: float) -> requests.Response:
                return requests.post(url, json=payload, headers=headers, timeout=timeout)

        # Post with minimal retry on 429/5xx
        try:
            resp = _post_once(self.timeout_sec)
            if 200 <= resp.status_code < 300:
                return True, ""
            if resp.status_code in (429, 500, 502, 503, 504):
                try:
                    time.sleep(1.0)
                except Exception:
                    pass
                resp2 = _post_once(self.timeout_sec)
                if 200 <= resp2.status_code < 300:
                    return True, ""
                return False, f"http_{resp2.status_code}:{(resp2.text or '')[:300]}"
            return False, f"http_{resp.status_code}:{(resp.text or '')[:300]}"
        except Exception as e:
            logger.error('webhook.error', traceback=traceback.format_exc())
            return False, str(e)

    def _notify_discord(self, *, url: str, payload: Dict[str, Any], fallback_text: str) -> Tuple[bool, str]:
        if not url:
            return False, "missing_discord_webhook_url"
        if not (str(url).startswith("http://") or str(url).startswith("https://")):
            return False, "invalid_discord_webhook_url"

        strategy = (payload or {}).get("strategy") or {}
        instrument = (payload or {}).get("instrument") or {}
        sig = (payload or {}).get("signal") or {}
        order = (payload or {}).get("order") or {}
        trace = (payload or {}).get("trace") or {}

        action = str(sig.get("action") or "").lower()
        color = 0x3498DB
        if action in ("open", "add"):
            color = 0x2ECC71
        if action in ("close", "reduce"):
            color = 0xE74C3C

        embed: Dict[str, Any] = {
            "title": "QuantDinger Signal",
            "color": int(color),
            "fields": [
                {"name": "Strategy", "value": f"{strategy.get('name') or ''} (#{int(strategy.get('id') or 0)})", "inline": True},
                {"name": "Symbol", "value": str(instrument.get("symbol") or ""), "inline": True},
                {"name": "Signal", "value": str(sig.get("type") or ""), "inline": False},
                {"name": "Price", "value": str(float(order.get('ref_price') or 0.0)), "inline": True},
                {"name": "Stake", "value": str(float(order.get('stake_amount') or 0.0)), "inline": True},
            ],
        }
        if payload.get("timestamp_iso"):
            embed["timestamp"] = str(payload.get("timestamp_iso") or "")
        if trace.get("pending_order_id"):
            embed["footer"] = {"text": f"pending_order_id={int(trace.get('pending_order_id'))}"}
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "QuantDinger/1.0 (+https://www.quantdinger.com)",
        }

        def _post(payload_json: Dict[str, Any]) -> requests.Response:
            return requests.post(url, json=payload_json, headers=headers, timeout=self.timeout_sec)

        try:
            resp = _post({"content": "", "embeds": [embed]})
            if 200 <= resp.status_code < 300:
                return True, ""

            # Rate limit: retry once if Discord asks us to.
            if resp.status_code == 429:
                try:
                    data = resp.json() if resp is not None else {}
                    retry_after = float((data or {}).get("retry_after") or 1.0)
                    time.sleep(min(max(retry_after, 0.5), 3.0))
                except Exception:
                    try:
                        time.sleep(1.0)
                    except Exception:
                        pass
                resp_retry = _post({"content": "", "embeds": [embed]})
                if 200 <= resp_retry.status_code < 300:
                    return True, ""
                resp = resp_retry

            # Fallback: plain text (some servers reject embeds)
            try:
                resp2 = _post({"content": str(fallback_text or "")[:1900]})
                if 200 <= resp2.status_code < 300:
                    return True, ""
                # If fallback also fails, return the original error (more useful than fallback sometimes).
            except Exception:
                pass
            return False, f"http_{resp.status_code}:{(resp.text or '')[:300]}"
        except Exception as e:
            logger.error('discord.error', traceback=traceback.format_exc())
            return False, str(e)

    def _notify_telegram(
        self,
        *,
        chat_id: str,
        text: str,
        token_override: str = "",
        parse_mode: str = "",
    ) -> Tuple[bool, str]:
        # 用户必须在个人中心配置自己的 telegram_bot_token
        token = (token_override or "").strip()
        if not token:
            return False, "missing_telegram_bot_token (请在个人中心配置 Telegram Bot Token)"
        if not chat_id:
            return False, "missing_telegram_chat_id"
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        try:
            data: Dict[str, Any] = {
                "chat_id": chat_id,
                "text": str(text or "")[:3900],
                "disable_web_page_preview": True,
            }
            if (parse_mode or "").strip():
                data["parse_mode"] = str(parse_mode).strip()
            resp = requests.post(
                url,
                data=data,
                timeout=self.timeout_sec,
            )
            if 200 <= resp.status_code < 300:
                return True, ""
            return False, f"http_{resp.status_code}:{(resp.text or '')[:300]}"
        except Exception as e:
            logger.error('telegram.error', traceback=traceback.format_exc())
            return False, str(e)

    def _notify_email(self, *, to_email: str, subject: str, body_text: str, body_html: str = "") -> Tuple[bool, str]:
        if not to_email:
            return False, "missing_email_target"
        if not self.smtp_host:
            return False, "missing_SMTP_HOST"
        if not self.smtp_from:
            return False, "missing_SMTP_FROM"

        msg = EmailMessage()
        msg["From"] = self.smtp_from
        msg["To"] = to_email
        msg["Subject"] = str(subject or "Signal")
        msg.set_content(str(body_text or ""))
        if (body_html or "").strip():
            msg.add_alternative(str(body_html or ""), subtype="html")

        try:
            # Heuristic: if port is 465 and SMTP_USE_SSL is not explicitly set, assume SSL.
            use_ssl = bool(self.smtp_use_ssl) or int(self.smtp_port or 0) == 465
            if use_ssl:
                with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=self.timeout_sec) as server:
                    server.ehlo()
                    if self.smtp_user and self.smtp_password:
                        server.login(self.smtp_user, self.smtp_password)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=self.timeout_sec) as server:
                    server.ehlo()
                    if self.smtp_use_tls:
                        server.starttls()
                        server.ehlo()
                    if self.smtp_user and self.smtp_password:
                        server.login(self.smtp_user, self.smtp_password)
                    server.send_message(msg)
            return True, ""
        except Exception as e:
            logger.error('email.error', traceback=traceback.format_exc())
            return False, str(e)

    def _notify_phone(self, *, to_phone: str, body: str) -> Tuple[bool, str]:
        # Optional provider: Twilio via REST (no extra dependency).
        if not to_phone:
            return False, "missing_phone_target"
        if not (self.twilio_sid and self.twilio_token and self.twilio_from):
            return False, "missing_TWILIO_config"
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.twilio_sid}/Messages.json"
        data = {"To": to_phone, "From": self.twilio_from, "Body": str(body or "")[:1500]}
        try:
            resp = requests.post(url, data=data, auth=(self.twilio_sid, self.twilio_token), timeout=self.timeout_sec)
            if 200 <= resp.status_code < 300:
                return True, ""
            return False, f"http_{resp.status_code}:{(resp.text or '')[:300]}"
        except Exception as e:
            logger.error('phone.error', traceback=traceback.format_exc())
            return False, str(e)


