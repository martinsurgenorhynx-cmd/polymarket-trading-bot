"""
Settings API - 读取和保存 .env 配置

Admin-only endpoints for system configuration management.
"""
import os
import re
from flask import Blueprint, request, jsonify
from app.utils.logger import get_logger
from app.utils.config_loader import clear_config_cache
from app.utils.auth import login_required, admin_required

logger = get_logger(__name__)

settings_bp = Blueprint('settings', __name__)

# .env 文件路径
ENV_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')

# 配置项定义（分组）- 按功能模块划分，每个配置项包含描述
# ---------------------------------------------------------------
# 精简原则：
#   - 部署级配置（host/port/debug）不在 UI 暴露，用户通过 .env 或 docker-compose 设置
#   - 内部调优参数（超时/重试/tick间隔/向量维度等）使用默认值即可，不暴露给普通用户
#   - 只保留用户真正需要配置的功能开关和 API Key
# ---------------------------------------------------------------
CONFIG_SCHEMA = {

    # ==================== 1. 安全认证 ====================
    'auth': {
        'title': 'Security & Authentication',
        'icon': 'lock',
        'order': 1,
        'items': [
            {
                'key': 'SECRET_KEY',
                'label': 'Secret Key',
                'type': 'password',
                'default': 'quantdinger-secret-key-change-me',
                'description': 'JWT signing secret key. MUST change in production for security'
            },
            {
                'key': 'ADMIN_USER',
                'label': 'Admin Username',
                'type': 'text',
                'default': 'quantdinger',
                'description': 'Administrator login username'
            },
            {
                'key': 'ADMIN_PASSWORD',
                'label': 'Admin Password',
                'type': 'password',
                'default': '123456',
                'description': 'Administrator login password. MUST change in production'
            },
            {
                'key': 'ADMIN_EMAIL',
                'label': 'Admin Email',
                'type': 'text',
                'default': 'admin@example.com',
                'description': 'Administrator email for password reset and notifications'
            },
        ]
    },

    # ==================== 2. AI/LLM 配置 ====================
    'ai': {
        'title': 'AI / LLM Configuration',
        'icon': 'robot',
        'order': 2,
        'items': [
            {
                'key': 'LLM_PROVIDER',
                'label': 'LLM Provider',
                'type': 'select',
                'default': 'openrouter',
                'options': [
                    {'value': 'openrouter', 'label': 'OpenRouter (Multi-model gateway)'},
                    {'value': 'openai', 'label': 'OpenAI Direct'},
                    {'value': 'google', 'label': 'Google Gemini'},
                    {'value': 'deepseek', 'label': 'DeepSeek'},
                    {'value': 'grok', 'label': 'xAI Grok'},
                ],
                'description': 'Select your preferred LLM provider'
            },
            # OpenRouter
            {
                'key': 'OPENROUTER_API_KEY',
                'label': 'OpenRouter API Key',
                'type': 'password',
                'required': False,
                'link': 'https://openrouter.ai/keys',
                'link_text': 'settings.link.getApiKey',
                'description': 'OpenRouter API key. Supports 100+ models via single API',
                'group': 'openrouter'
            },
            {
                'key': 'OPENROUTER_MODEL',
                'label': 'OpenRouter Model',
                'type': 'text',
                'default': 'openai/gpt-4o',
                'link': 'https://openrouter.ai/models',
                'link_text': 'settings.link.viewModels',
                'description': 'Model ID, e.g. openai/gpt-4o, anthropic/claude-3.5-sonnet',
                'group': 'openrouter'
            },
            # OpenAI Direct
            {
                'key': 'OPENAI_API_KEY',
                'label': 'OpenAI API Key',
                'type': 'password',
                'required': False,
                'link': 'https://platform.openai.com/api-keys',
                'link_text': 'settings.link.getApiKey',
                'description': 'OpenAI official API key',
                'group': 'openai'
            },
            {
                'key': 'OPENAI_MODEL',
                'label': 'OpenAI Model',
                'type': 'text',
                'default': 'gpt-4o',
                'description': 'Model name: gpt-4o, gpt-4o-mini, gpt-4-turbo, etc.',
                'group': 'openai'
            },
            {
                'key': 'OPENAI_BASE_URL',
                'label': 'OpenAI Base URL',
                'type': 'text',
                'default': 'https://api.openai.com/v1',
                'description': 'Custom API endpoint (for proxies or Azure)',
                'group': 'openai'
            },
            # Google Gemini
            {
                'key': 'GOOGLE_API_KEY',
                'label': 'Google API Key',
                'type': 'password',
                'required': False,
                'link': 'https://aistudio.google.com/apikey',
                'link_text': 'settings.link.getApiKey',
                'description': 'Google AI Studio API key for Gemini',
                'group': 'google'
            },
            {
                'key': 'GOOGLE_MODEL',
                'label': 'Gemini Model',
                'type': 'text',
                'default': 'gemini-1.5-flash',
                'description': 'Model: gemini-1.5-flash, gemini-1.5-pro, gemini-2.0-flash-exp',
                'group': 'google'
            },
            # DeepSeek
            {
                'key': 'DEEPSEEK_API_KEY',
                'label': 'DeepSeek API Key',
                'type': 'password',
                'required': False,
                'link': 'https://platform.deepseek.com/api_keys',
                'link_text': 'settings.link.getApiKey',
                'description': 'DeepSeek API key',
                'group': 'deepseek'
            },
            {
                'key': 'DEEPSEEK_MODEL',
                'label': 'DeepSeek Model',
                'type': 'text',
                'default': 'deepseek-chat',
                'description': 'Model: deepseek-chat, deepseek-coder',
                'group': 'deepseek'
            },
            {
                'key': 'DEEPSEEK_BASE_URL',
                'label': 'DeepSeek Base URL',
                'type': 'text',
                'default': 'https://api.deepseek.com/v1',
                'description': 'DeepSeek API endpoint',
                'group': 'deepseek'
            },
            # xAI Grok
            {
                'key': 'GROK_API_KEY',
                'label': 'Grok API Key',
                'type': 'password',
                'required': False,
                'link': 'https://console.x.ai/',
                'link_text': 'settings.link.getApiKey',
                'description': 'xAI Grok API key',
                'group': 'grok'
            },
            {
                'key': 'GROK_MODEL',
                'label': 'Grok Model',
                'type': 'text',
                'default': 'grok-beta',
                'description': 'Model: grok-beta, grok-2',
                'group': 'grok'
            },
            {
                'key': 'GROK_BASE_URL',
                'label': 'Grok Base URL',
                'type': 'text',
                'default': 'https://api.x.ai/v1',
                'description': 'xAI Grok API endpoint',
                'group': 'grok'
            },
            # Common settings
            {
                'key': 'OPENROUTER_TEMPERATURE',
                'label': 'Temperature',
                'type': 'number',
                'default': '0.7',
                'description': 'Model creativity (0-1). Lower = more deterministic'
            },
            {
                'key': 'AI_MODELS_JSON',
                'label': 'Custom Models (JSON)',
                'type': 'text',
                'default': '{}',
                'required': False,
                'description': 'Custom model list in JSON format for model selector'
            },
        ]
    },

    # ==================== 3. 实盘交易 ====================
    'trading': {
        'title': 'Live Trading',
        'icon': 'stock',
        'order': 3,
        'items': [
            {
                'key': 'ORDER_MODE',
                'label': 'Order Execution Mode',
                'type': 'select',
                'options': ['market', 'maker'],
                'default': 'market',
                'description': 'market: Market order (instant fill, recommended), maker: Limit order first (lower fees but may not fill)'
            },
            {
                'key': 'MAKER_WAIT_SEC',
                'label': 'Limit Order Wait (sec)',
                'type': 'number',
                'default': '10',
                'description': 'Wait time for limit order fill before switching to market order'
            },
        ]
    },

    # ==================== 4. 数据源配置 ====================
    'data_source': {
        'title': 'Data Sources',
        'icon': 'database',
        'order': 4,
        'items': [
            {
                'key': 'CCXT_DEFAULT_EXCHANGE',
                'label': 'Default Crypto Exchange',
                'type': 'text',
                'default': 'coinbase',
                'link': 'https://github.com/ccxt/ccxt#supported-cryptocurrency-exchange-markets',
                'link_text': 'settings.link.supportedExchanges',
                'description': 'Default exchange for crypto data (binance, coinbase, okx, etc.)'
            },
            {
                'key': 'CCXT_PROXY',
                'label': 'Crypto Data Proxy',
                'type': 'text',
                'required': False,
                'description': 'Proxy URL for crypto data requests (e.g. socks5h://127.0.0.1:1080)'
            },
            {
                'key': 'FINNHUB_API_KEY',
                'label': 'Finnhub API Key',
                'type': 'password',
                'required': False,
                'link': 'https://finnhub.io/register',
                'link_text': 'settings.link.freeRegister',
                'description': 'Finnhub API key for US stock data (free tier available)'
            },
            {
                'key': 'TIINGO_API_KEY',
                'label': 'Tiingo API Key',
                'type': 'password',
                'required': False,
                'link': 'https://www.tiingo.com/account/api/token',
                'link_text': 'settings.link.getToken',
                'description': 'Tiingo API key for Forex/Metals data'
            },
        ]
    },

    # ==================== 5. 邮件配置 ====================
    'email': {
        'title': 'Email (SMTP)',
        'icon': 'mail',
        'order': 5,
        'items': [
            {
                'key': 'SMTP_HOST',
                'label': 'SMTP Server',
                'type': 'text',
                'required': False,
                'description': 'SMTP server hostname (e.g. smtp.gmail.com)'
            },
            {
                'key': 'SMTP_PORT',
                'label': 'SMTP Port',
                'type': 'number',
                'default': '587',
                'description': 'SMTP port (587 for TLS, 465 for SSL)'
            },
            {
                'key': 'SMTP_USER',
                'label': 'SMTP Username',
                'type': 'text',
                'required': False,
                'description': 'SMTP authentication username (usually email address)'
            },
            {
                'key': 'SMTP_PASSWORD',
                'label': 'SMTP Password',
                'type': 'password',
                'required': False,
                'description': 'SMTP authentication password or app-specific password'
            },
            {
                'key': 'SMTP_FROM',
                'label': 'Sender Address',
                'type': 'text',
                'required': False,
                'description': 'Email sender address (From header)'
            },
            {
                'key': 'SMTP_USE_TLS',
                'label': 'Use TLS',
                'type': 'boolean',
                'default': 'True',
                'description': 'Enable STARTTLS encryption (recommended for port 587)'
            },
            {
                'key': 'SMTP_USE_SSL',
                'label': 'Use SSL',
                'type': 'boolean',
                'default': 'False',
                'description': 'Enable SSL encryption (for port 465)'
            },
        ]
    },

    # ==================== 6. 短信配置 ====================
    'sms': {
        'title': 'SMS (Twilio)',
        'icon': 'phone',
        'order': 6,
        'items': [
            {
                'key': 'TWILIO_ACCOUNT_SID',
                'label': 'Account SID',
                'type': 'password',
                'required': False,
                'link': 'https://console.twilio.com/',
                'link_text': 'settings.link.getApi',
                'description': 'Twilio Account SID from console dashboard'
            },
            {
                'key': 'TWILIO_AUTH_TOKEN',
                'label': 'Auth Token',
                'type': 'password',
                'required': False,
                'description': 'Twilio Auth Token from console dashboard'
            },
            {
                'key': 'TWILIO_FROM_NUMBER',
                'label': 'Sender Number',
                'type': 'text',
                'required': False,
                'description': 'Twilio phone number for sending SMS (e.g. +1234567890)'
            },
        ]
    },

    # ==================== 7. AI Agent ====================
    'agent': {
        'title': 'AI Agent',
        'icon': 'experiment',
        'order': 7,
        'items': [
            {
                'key': 'ENABLE_AGENT_MEMORY',
                'label': 'Enable Agent Memory',
                'type': 'boolean',
                'default': 'True',
                'description': 'Enable AI agent memory for learning from past trades'
            },
            {
                'key': 'ENABLE_REFLECTION_WORKER',
                'label': 'Enable Auto Reflection',
                'type': 'boolean',
                'default': 'False',
                'description': 'Enable background worker for automatic trade reflection'
            },
        ]
    },

    # ==================== 8. 网络代理 ====================
    'network': {
        'title': 'Network & Proxy',
        'icon': 'global',
        'order': 8,
        'items': [
            {
                'key': 'PROXY_URL',
                'label': 'Proxy URL',
                'type': 'text',
                'required': False,
                'description': 'Global proxy URL (e.g. socks5h://127.0.0.1:1080 or http://proxy:8080)'
            },
        ]
    },

    # ==================== 9. 搜索配置 ====================
    'search': {
        'title': 'Web Search',
        'icon': 'search',
        'order': 9,
        'items': [
            {
                'key': 'SEARCH_PROVIDER',
                'label': 'Search Provider',
                'type': 'select',
                'options': ['bocha', 'tavily', 'google', 'bing', 'none'],
                'default': 'bocha',
                'description': 'Web search provider for AI research features'
            },
            {
                'key': 'TAVILY_API_KEYS',
                'label': 'Tavily API Keys',
                'type': 'password',
                'required': False,
                'link': 'https://tavily.com/',
                'link_text': 'settings.link.getApiKey',
                'description': 'Tavily Search API keys (comma-separated). Free 1000 req/month'
            },
            {
                'key': 'BOCHA_API_KEYS',
                'label': 'Bocha API Keys',
                'type': 'password',
                'required': False,
                'link': 'https://bochaai.com/',
                'link_text': 'settings.link.getApiKey',
                'description': 'Bocha Search API keys (comma-separated)'
            },
        ]
    },

    # ==================== 10. 注册与 OAuth ====================
    'security': {
        'title': 'Registration & OAuth',
        'icon': 'safety',
        'order': 10,
        'items': [
            {
                'key': 'ENABLE_REGISTRATION',
                'label': 'Enable Registration',
                'type': 'boolean',
                'default': 'True',
                'description': 'Allow new users to register accounts'
            },
            {
                'key': 'FRONTEND_URL',
                'label': 'Frontend URL',
                'type': 'text',
                'default': 'http://localhost:8080',
                'description': 'Frontend URL for OAuth redirects'
            },
            {
                'key': 'TURNSTILE_SITE_KEY',
                'label': 'Turnstile Site Key',
                'type': 'text',
                'required': False,
                'link': 'https://dash.cloudflare.com/?to=/:account/turnstile',
                'link_text': 'settings.link.getTurnstileKey',
                'description': 'Cloudflare Turnstile site key for CAPTCHA'
            },
            {
                'key': 'TURNSTILE_SECRET_KEY',
                'label': 'Turnstile Secret Key',
                'type': 'password',
                'required': False,
                'description': 'Cloudflare Turnstile secret key'
            },
            {
                'key': 'GOOGLE_CLIENT_ID',
                'label': 'Google OAuth Client ID',
                'type': 'text',
                'required': False,
                'link': 'https://console.cloud.google.com/apis/credentials',
                'link_text': 'settings.link.getGoogleCredentials',
                'description': 'Google OAuth Client ID for Google login'
            },
            {
                'key': 'GOOGLE_CLIENT_SECRET',
                'label': 'Google OAuth Secret',
                'type': 'password',
                'required': False,
                'description': 'Google OAuth Client Secret'
            },
            {
                'key': 'GITHUB_CLIENT_ID',
                'label': 'GitHub OAuth Client ID',
                'type': 'text',
                'required': False,
                'link': 'https://github.com/settings/developers',
                'link_text': 'settings.link.getGithubCredentials',
                'description': 'GitHub OAuth Client ID for GitHub login'
            },
            {
                'key': 'GITHUB_CLIENT_SECRET',
                'label': 'GitHub OAuth Secret',
                'type': 'password',
                'required': False,
                'description': 'GitHub OAuth Client Secret'
            },
        ]
    },

    # ==================== 11. 计费配置 ====================
    'billing': {
        'title': 'Billing & Credits',
        'icon': 'dollar',
        'order': 11,
        'items': [
            {
                'key': 'BILLING_ENABLED',
                'label': 'Enable Billing',
                'type': 'boolean',
                'default': 'False',
                'description': 'Enable billing system. Users need credits to use certain features'
            },
            {
                'key': 'BILLING_VIP_BYPASS',
                'label': 'VIP Bypass (Legacy)',
                'type': 'boolean',
                'default': 'False',
                'description': 'Legacy switch. If enabled, VIP users bypass ALL feature credit costs. Recommended OFF: VIP should only unlock VIP-free indicators.'
            },

            # ===== Membership Plans (3 tiers) =====
            {
                'key': 'MEMBERSHIP_MONTHLY_PRICE_USD',
                'label': 'Monthly Membership Price (USD)',
                'type': 'number',
                'default': '19.9',
                'description': 'Monthly membership price in USD (mock payment in current version)'
            },
            {
                'key': 'MEMBERSHIP_MONTHLY_CREDITS',
                'label': 'Monthly Membership Bonus Credits',
                'type': 'number',
                'default': '500',
                'description': 'Credits granted immediately after purchasing monthly membership'
            },
            {
                'key': 'MEMBERSHIP_YEARLY_PRICE_USD',
                'label': 'Yearly Membership Price (USD)',
                'type': 'number',
                'default': '199',
                'description': 'Yearly membership price in USD (mock payment in current version)'
            },
            {
                'key': 'MEMBERSHIP_YEARLY_CREDITS',
                'label': 'Yearly Membership Bonus Credits',
                'type': 'number',
                'default': '8000',
                'description': 'Credits granted immediately after purchasing yearly membership'
            },
            {
                'key': 'MEMBERSHIP_LIFETIME_PRICE_USD',
                'label': 'Lifetime Membership Price (USD)',
                'type': 'number',
                'default': '499',
                'description': 'Lifetime membership price in USD (mock payment in current version)'
            },
            {
                'key': 'MEMBERSHIP_LIFETIME_MONTHLY_CREDITS',
                'label': 'Lifetime Membership Monthly Credits',
                'type': 'number',
                'default': '800',
                'description': 'Credits granted every 30 days for lifetime members'
            },

            # ===== USDT Pay (方案B：每单独立地址) =====
            {
                'key': 'USDT_PAY_ENABLED',
                'label': 'Enable USDT Pay',
                'type': 'boolean',
                'default': 'False',
                'description': 'Enable USDT scan-to-pay flow (per-order unique address)'
            },
            {
                'key': 'USDT_PAY_CHAIN',
                'label': 'USDT Chain',
                'type': 'select',
                'default': 'TRC20',
                'options': ['TRC20'],
                'description': 'Currently only TRC20 is supported'
            },
            {
                'key': 'USDT_TRC20_XPUB',
                'label': 'TRC20 XPUB (Watch-only)',
                'type': 'password',
                'required': False,
                'description': 'Watch-only xpub used to derive per-order deposit addresses. Do NOT paste private key.'
            },
            {
                'key': 'USDT_TRC20_CONTRACT',
                'label': 'USDT TRC20 Contract',
                'type': 'text',
                'default': 'TXLAQ63Xg1NAzckPwKHvzw7CSEmLMEqcdj',
                'description': 'USDT contract address on TRON'
            },
            {
                'key': 'TRONGRID_BASE_URL',
                'label': 'TronGrid Base URL',
                'type': 'text',
                'default': 'https://api.trongrid.io',
                'description': 'TronGrid API base URL'
            },
            {
                'key': 'TRONGRID_API_KEY',
                'label': 'TronGrid API Key',
                'type': 'password',
                'required': False,
                'description': 'Optional TronGrid API key for higher rate limits'
            },
            {
                'key': 'USDT_PAY_CONFIRM_SECONDS',
                'label': 'Confirm Delay (sec)',
                'type': 'number',
                'default': '30',
                'description': 'Delay before marking a paid transaction as confirmed (TRC20)'
            },
            {
                'key': 'USDT_PAY_EXPIRE_MINUTES',
                'label': 'Order Expire (min)',
                'type': 'number',
                'default': '30',
                'description': 'USDT payment order expiration time in minutes'
            },
            {
                'key': 'BILLING_COST_AI_ANALYSIS',
                'label': 'AI Analysis Cost',
                'type': 'number',
                'default': '10',
                'description': 'Credits per AI analysis request'
            },
            {
                'key': 'BILLING_COST_STRATEGY_RUN',
                'label': 'Strategy Run Cost',
                'type': 'number',
                'default': '5',
                'description': 'Credits per strategy start'
            },
            {
                'key': 'BILLING_COST_BACKTEST',
                'label': 'Backtest Cost',
                'type': 'number',
                'default': '3',
                'description': 'Credits per backtest run'
            },
            {
                'key': 'BILLING_COST_PORTFOLIO_MONITOR',
                'label': 'Portfolio Monitor Cost',
                'type': 'number',
                'default': '8',
                'description': 'Credits per portfolio AI monitoring run'
            },
            {
                'key': 'RECHARGE_TELEGRAM_URL',
                'label': 'Recharge Telegram URL',
                'type': 'text',
                'default': 'https://t.me/your_support_bot',
                'description': 'Telegram URL for recharge inquiries'
            },
            {
                'key': 'CREDITS_REGISTER_BONUS',
                'label': 'Register Bonus',
                'type': 'number',
                'default': '100',
                'description': 'Credits awarded to new users on registration'
            },
            {
                'key': 'CREDITS_REFERRAL_BONUS',
                'label': 'Referral Bonus',
                'type': 'number',
                'default': '50',
                'description': 'Credits awarded to referrer for each signup'
            },
        ]
    },

    # ==================== 12. 应用功能 ====================
    'app': {
        'title': 'Application',
        'icon': 'appstore',
        'order': 12,
        'items': [
            {
                'key': 'CORS_ORIGINS',
                'label': 'CORS Origins',
                'type': 'text',
                'default': '*',
                'description': 'Allowed CORS origins (* for all, or comma-separated URLs)'
            },
            {
                'key': 'ENABLE_AI_ANALYSIS',
                'label': 'Enable AI Analysis',
                'type': 'boolean',
                'default': 'True',
                'description': 'Enable AI-powered market analysis features'
            },
        ]
    },
}


def read_env_file():
    """读取 .env 文件"""
    env_values = {}
    
    if not os.path.exists(ENV_FILE_PATH):
        logger.warning(f".env file not found at {ENV_FILE_PATH}")
        return env_values
    
    try:
        with open(ENV_FILE_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # 跳过空行和注释
                if not line or line.startswith('#'):
                    continue
                # 解析 KEY=VALUE
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    # 移除引号
                    if (value.startswith('"') and value.endswith('"')) or \
                       (value.startswith("'") and value.endswith("'")):
                        value = value[1:-1]
                    env_values[key] = value
    except Exception as e:
        logger.error(f"Failed to read .env file: {e}")
    
    return env_values


def write_env_file(env_values):
    """写入 .env 文件，保留注释和格式"""
    lines = []
    existing_keys = set()
    
    # 读取原文件保留格式
    if os.path.exists(ENV_FILE_PATH):
        try:
            with open(ENV_FILE_PATH, 'r', encoding='utf-8') as f:
                for line in f:
                    original_line = line
                    stripped = line.strip()
                    
                    # 保留空行和注释
                    if not stripped or stripped.startswith('#'):
                        lines.append(original_line)
                        continue
                    
                    # 更新已存在的键
                    if '=' in stripped:
                        key = stripped.split('=', 1)[0].strip()
                        if key in env_values:
                            existing_keys.add(key)
                            value = env_values[key]
                            # 如果值包含特殊字符，用引号包裹
                            if ' ' in str(value) or '"' in str(value) or "'" in str(value):
                                lines.append(f'{key}="{value}"\n')
                            else:
                                lines.append(f'{key}={value}\n')
                        else:
                            lines.append(original_line)
                    else:
                        lines.append(original_line)
        except Exception as e:
            logger.error(f"Failed to read .env file for update: {e}")
    
    # 添加新的键
    new_keys = set(env_values.keys()) - existing_keys
    if new_keys:
        if lines and not lines[-1].endswith('\n'):
            lines.append('\n')
        lines.append('\n# Added by Settings UI\n')
        for key in sorted(new_keys):
            value = env_values[key]
            if ' ' in str(value) or '"' in str(value) or "'" in str(value):
                lines.append(f'{key}="{value}"\n')
            else:
                lines.append(f'{key}={value}\n')
    
    # 写入文件
    try:
        with open(ENV_FILE_PATH, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        return True
    except Exception as e:
        logger.error(f"Failed to write .env file: {e}")
        return False


@settings_bp.route('/schema', methods=['GET'])
@login_required
@admin_required
def get_settings_schema():
    """获取配置项定义 (admin only)"""
    return jsonify({
        'code': 1,
        'msg': 'success',
        'data': CONFIG_SCHEMA
    })


@settings_bp.route('/values', methods=['GET'])
@login_required
@admin_required
def get_settings_values():
    """获取当前配置值 - 包括敏感信息（真实值）(admin only)"""
    env_values = read_env_file()
    
    # 构建返回数据，返回真实值
    result = {}
    for group_key, group in CONFIG_SCHEMA.items():
        result[group_key] = {}
        for item in group['items']:
            key = item['key']
            value = env_values.get(key, item.get('default', ''))
            result[group_key][key] = value
            # 标记密码类型是否已配置
            if item['type'] == 'password':
                result[group_key][f'{key}_configured'] = bool(value)
    
    return jsonify({
        'code': 1,
        'msg': 'success',
        'data': result
    })


@settings_bp.route('/save', methods=['POST'])
@login_required
@admin_required
def save_settings():
    """保存配置 (admin only)"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'code': 0, 'msg': 'Invalid request payload'})
        
        # 读取当前配置
        current_env = read_env_file()
        
        # 更新配置
        updates = {}
        for group_key, group_values in data.items():
            if group_key not in CONFIG_SCHEMA:
                continue
            
            for item in CONFIG_SCHEMA[group_key]['items']:
                key = item['key']
                if key in group_values:
                    new_value = group_values[key]
                    
                    # 空值处理
                    if new_value is None or new_value == '':
                        if not item.get('required', True):
                            updates[key] = ''
                    else:
                        updates[key] = str(new_value)
        
        # 合并更新
        current_env.update(updates)
        
        # 写入文件
        if write_env_file(current_env):
            # 清除配置缓存
            clear_config_cache()
            
            return jsonify({
                'code': 1,
                'msg': 'Settings saved successfully',
                'data': {
                    'updated_keys': list(updates.keys()),
                    'requires_restart': True  # 标记需要重启
                }
            })
        else:
            return jsonify({'code': 0, 'msg': 'Failed to save settings'})
    
    except Exception as e:
        logger.error(f"Failed to save settings: {e}")
        return jsonify({'code': 0, 'msg': f'Save failed: {str(e)}'})


@settings_bp.route('/openrouter-balance', methods=['GET'])
@login_required
@admin_required
def get_openrouter_balance():
    """查询 OpenRouter 账户余额 (admin only)"""
    try:
        import requests
        from app.config.api_keys import APIKeys
        
        api_key = APIKeys.OPENROUTER_API_KEY
        if not api_key:
            return jsonify({
                'code': 0, 
                'msg': 'OpenRouter API Key 未配置',
                'data': None
            })
        
        # 调用 OpenRouter API 查询余额
        # https://openrouter.ai/docs#limits
        resp = requests.get(
            'https://openrouter.ai/api/v1/auth/key',
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            },
            timeout=10
        )
        
        if resp.status_code == 200:
            data = resp.json()
            # OpenRouter 返回格式: {"data": {"label": "...", "usage": 0.0, "limit": null, ...}}
            key_data = data.get('data', {})
            usage = key_data.get('usage', 0)  # 已使用金额
            limit = key_data.get('limit')  # 限额（可能为null表示无限制）
            limit_remaining = key_data.get('limit_remaining')  # 剩余额度
            is_free_tier = key_data.get('is_free_tier', False)
            rate_limit = key_data.get('rate_limit', {})
            
            return jsonify({
                'code': 1,
                'msg': 'success',
                'data': {
                    'usage': round(usage, 4),  # 已使用（美元）
                    'limit': limit,  # 总限额
                    'limit_remaining': round(limit_remaining, 4) if limit_remaining is not None else None,  # 剩余额度
                    'is_free_tier': is_free_tier,
                    'rate_limit': rate_limit,
                    'label': key_data.get('label', '')
                }
            })
        elif resp.status_code == 401:
            return jsonify({
                'code': 0,
                'msg': 'API Key 无效或已过期',
                'data': None
            })
        else:
            return jsonify({
                'code': 0,
                'msg': f'查询失败: HTTP {resp.status_code}',
                'data': None
            })
            
    except requests.exceptions.Timeout:
        return jsonify({
            'code': 0,
            'msg': '请求超时，请检查网络连接',
            'data': None
        })
    except Exception as e:
        logger.error(f"Get OpenRouter balance failed: {e}")
        return jsonify({
            'code': 0,
            'msg': f'查询失败: {str(e)}',
            'data': None
        })


@settings_bp.route('/test-connection', methods=['POST'])
@login_required
@admin_required
def test_connection():
    """测试API连接 (admin only)"""
    try:
        data = request.get_json()
        service = data.get('service')
        
        if service == 'openrouter':
            # 测试 OpenRouter 连接
            from app.services.llm import LLMService
            llm = LLMService()
            result = llm.test_connection()
            if result:
                return jsonify({'code': 1, 'msg': 'OpenRouter connection successful'})
            else:
                return jsonify({'code': 0, 'msg': 'OpenRouter connection failed'})
        
        elif service == 'finnhub':
            # 测试 Finnhub 连接
            import requests
            api_key = data.get('api_key') or os.getenv('FINNHUB_API_KEY')
            if not api_key:
                return jsonify({'code': 0, 'msg': 'API key is not configured'})
            resp = requests.get(
                f'https://finnhub.io/api/v1/quote?symbol=AAPL&token={api_key}',
                timeout=10
            )
            if resp.status_code == 200:
                return jsonify({'code': 1, 'msg': 'Finnhub connection successful'})
            else:
                return jsonify({'code': 0, 'msg': f'Finnhub connection failed: {resp.status_code}'})
        
        return jsonify({'code': 0, 'msg': 'Unknown service'})
    
    except Exception as e:
        logger.error(f"Connection test failed: {e}")
        return jsonify({'code': 0, 'msg': f'Test failed: {str(e)}'})
