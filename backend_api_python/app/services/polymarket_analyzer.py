"""
Polymarket预测市场分析器
分析预测市场，生成AI预测和交易机会推荐
"""
import json
import re
from typing import Dict, List, Any, Optional
from datetime import datetime

from app.utils.logger import get_logger
from app.utils.db import get_db_connection
from app.services.llm import LLMService
from app.services.market_data_collector import get_market_data_collector
from app.data_sources.polymarket import PolymarketDataSource

logger = get_logger(__name__)


class PolymarketAnalyzer:
    """预测市场AI分析器"""
    
    def __init__(self):
        self.llm_service = LLMService()
        self.data_collector = get_market_data_collector()
        self.polymarket_source = PolymarketDataSource()
    
    def analyze_market(self, market_id: str, user_id: int = None, use_cache: bool = True, language: str = 'zh-CN', model: str = None) -> Dict:
        """
        分析单个预测市场
        
        Args:
            market_id: 市场ID
            user_id: 用户ID（可选，用于用户特定分析）
            use_cache: 是否使用缓存的分析结果（默认True）
            language: 语言设置（'zh-CN' 或 'en-US'），用于生成对应语言的AI分析结果
            
        Returns:
            分析结果字典
        """
        try:
            # 1. 获取市场数据
            market = self.polymarket_source.get_market_details(market_id)
            if not market:
                return {
                    "error": "Market not found",
                    "market_id": market_id
                }
            
            # 2. 如果使用缓存，检查是否有缓存的分析结果（30分钟有效）
            if use_cache:
                cached_analysis = self._get_cached_analysis(market_id, user_id)
                if cached_analysis:
                    cache_minutes = 30  # 缓存30分钟
                    if self._is_analysis_fresh(cached_analysis, max_age_minutes=cache_minutes):
                        logger.debug(f"Using cached analysis for market {market_id}")
                        return cached_analysis
            
            # 3. 收集相关数据
            related_news = self._get_related_news(market['question'])
            related_assets = self._identify_related_assets(market['question'])
            asset_data = self._get_asset_data(related_assets)
            
            # 4. AI分析
            ai_result = self._ai_predict_probability(
                question=market['question'],
                current_market_prob=market['current_probability'],
                related_news=related_news,
                asset_data=asset_data,
                language=language
            )
            
            # 5. 计算机会评分
            opportunity_score = self._calculate_opportunity_score(
                ai_prob=ai_result['predicted_probability'],
                market_prob=market['current_probability'],
                confidence=ai_result['confidence']
            )
            
            # 6. 生成推荐
            recommendation = self._generate_recommendation(
                divergence=ai_result['predicted_probability'] - market['current_probability'],
                confidence=ai_result['confidence']
            )
            
            # 7. 构建分析结果
            analysis_result = {
                "market_id": market_id,
                "ai_predicted_probability": ai_result['predicted_probability'],
                "market_probability": market['current_probability'],
                "divergence": ai_result['predicted_probability'] - market['current_probability'],
                "recommendation": recommendation,
                "confidence_score": ai_result['confidence'],
                "reasoning": ai_result['reasoning'],
                "key_factors": ai_result.get('key_factors', []),
                "risk_factors": ai_result.get('risk_factors', []),
                "related_assets": related_assets,
                "risk_level": self._assess_risk(market, ai_result),
                "opportunity_score": opportunity_score
            }
            
            # 8. 保存到数据库
            self._save_analysis_to_db(analysis_result, user_id)
            
            return analysis_result
            
        except Exception as e:
            logger.error(f"Failed to analyze market {market_id}: {e}", exc_info=True)
            return {
                "error": str(e),
                "market_id": market_id
            }
    
    def generate_asset_trading_opportunities(self, market_id: str) -> List[Dict]:
        """
        基于预测市场生成相关资产的交易机会
        
        Args:
            market_id: 预测市场ID
            
        Returns:
            资产交易机会列表
        """
        try:
            # 1. 分析预测市场
            market_analysis = self.analyze_market(market_id)
            if market_analysis.get('error'):
                return []
            
            # 2. 识别相关资产
            related_assets = market_analysis.get('related_assets', [])
            if not related_assets:
                return []
            
            # 3. 对每个资产进行技术分析
            opportunities = []
            for asset in related_assets:
                try:
                    # 推断市场类型
                    market_type = self._infer_market(asset)
                    
                    # 获取资产数据
                    asset_data = self.data_collector.collect_all(
                        market=market_type,
                        symbol=asset,
                        timeframe="1D",
                        include_polymarket=False  # 避免循环
                    )
                    
                    # 技术分析
                    technical_analysis = self._analyze_technical(asset_data)
                    
                    # 结合预测市场信号
                    if market_analysis['recommendation'] == "YES":
                        # 预测事件发生概率高 → 相关资产可能上涨
                        signal = "BUY" if technical_analysis.get('trend') == "bullish" else "HOLD"
                    elif market_analysis['recommendation'] == "NO":
                        # 预测事件发生概率低 → 相关资产可能下跌
                        signal = "SELL" if technical_analysis.get('trend') == "bearish" else "HOLD"
                    else:
                        signal = "HOLD"
                    
                    # 计算综合置信度
                    confidence = (
                        market_analysis['confidence_score'] * 0.6 + 
                        technical_analysis.get('confidence', 50) * 0.4
                    )
                    
                    if signal != "HOLD" and confidence > 60:
                        opportunities.append({
                            "asset": asset,
                            "market": market_type,
                            "signal": signal,
                            "confidence": round(confidence, 2),
                            "reasoning": f"预测市场分析：{market_analysis['reasoning'][:200]}。技术面：{technical_analysis.get('summary', '')[:200]}",
                            "related_prediction": {
                                "market_id": market_id,
                                "question": market_analysis.get('question', ''),
                                "ai_probability": market_analysis['ai_predicted_probability'],
                                "market_probability": market_analysis['market_probability']
                            },
                            "entry_suggestion": technical_analysis.get('entry_suggestion', {})
                        })
                except Exception as e:
                    logger.debug(f"Failed to analyze asset {asset} for market {market_id}: {e}")
                    continue
            
            # 保存机会到数据库
            if opportunities:
                self._save_opportunities_to_db(market_id, opportunities)
            
            return opportunities
            
        except Exception as e:
            logger.error(f"Failed to generate asset opportunities for {market_id}: {e}")
            return []
    
    def _ai_predict_probability(self, question: str, current_market_prob: float,
                                related_news: List, asset_data: Dict, language: str = 'zh-CN') -> Dict:
        """使用AI预测事件概率"""
        try:
            # 根据语言设置构建prompt
            is_english = language.lower() in ['en', 'en-us', 'en_us']
            
            # 构建prompt
            news_text = "\n".join([f"- {n.get('title', '')[:100]}" for n in related_news[:5]])
            
            asset_text = ""
            if asset_data:
                price_data = asset_data.get('price', {})
                indicators = asset_data.get('indicators', {})
                if price_data:
                    if is_english:
                        asset_text = f"""
Related Asset Data:
- Current Price: {price_data.get('current_price', 'N/A')}
- 24h Change: {price_data.get('change_24h', 0):.2f}%
- RSI: {indicators.get('rsi', {}).get('value', 'N/A')}
- MACD: {indicators.get('macd', {}).get('signal', 'N/A')}
"""
                    else:
                        asset_text = f"""
相关资产数据：
- 当前价格: {price_data.get('current_price', 'N/A')}
- 24h涨跌幅: {price_data.get('change_24h', 0):.2f}%
- RSI: {indicators.get('rsi', {}).get('value', 'N/A')}
- MACD: {indicators.get('macd', {}).get('signal', 'N/A')}
"""
            
            if is_english:
                prompt = f"""Analyze the following prediction market event and assess its probability of occurrence:

Question: {question}
Current Market Probability: {current_market_prob}%

Related News:
{news_text if news_text else "No related news available"}

{asset_text}

Please analyze based on the following dimensions:
1. Success rate of similar historical events
2. Current news and trends
3. Related asset price movements and technical indicators
4. Macro environment factors (VIX, DXY, interest rates, etc.)
5. Market sentiment indicators

Output JSON format:
{{
    "predicted_probability": 72.5,  // Your predicted probability (0-100)
    "confidence": 75.0,  // Confidence level (0-100)
    "reasoning": "Detailed analysis...",
    "key_factors": ["Factor 1", "Factor 2"],
    "risk_factors": ["Risk 1", "Risk 2"]
}}

IMPORTANT: All text in the JSON response (reasoning, key_factors, risk_factors) must be in English."""
                
                system_prompt = "You are a professional market analyst specializing in prediction market analysis. Please objectively assess the probability of events occurring based on the provided data. Respond in English."
            else:
                prompt = f"""分析以下预测市场事件，评估其发生的概率：

问题：{question}
当前市场概率：{current_market_prob}%

相关新闻：
{news_text if news_text else "暂无相关新闻"}

{asset_text}

请基于以下维度分析：
1. 历史类似事件的成功率
2. 当前新闻和趋势
3. 相关资产价格走势和技术指标
4. 宏观环境因素（VIX、DXY、利率等）
5. 市场情绪指标

输出JSON格式：
{{
    "predicted_probability": 72.5,  // 你预测的概率（0-100）
    "confidence": 75.0,  // 置信度（0-100）
    "reasoning": "详细分析...",
    "key_factors": ["因素1", "因素2"],
    "risk_factors": ["风险1", "风险2"]
}}

重要提示：JSON响应中的所有文本（reasoning、key_factors、risk_factors）必须使用中文。"""
                
                system_prompt = "你是一个专业的市场分析师，擅长分析预测市场事件。请基于提供的数据，客观评估事件发生的概率。请使用中文回答。"
            
            # 调用LLM
            messages = [
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]
            
            result = self.llm_service.call_llm_api(
                messages=messages,
                use_json_mode=True,
                temperature=0.3
            )
            
            # 解析结果
            if isinstance(result, str):
                result = json.loads(result)
            
            # 验证和规范化
            predicted_prob = float(result.get('predicted_probability', current_market_prob))
            predicted_prob = max(0, min(100, predicted_prob))  # 限制在0-100
            
            confidence = float(result.get('confidence', 70))
            confidence = max(0, min(100, confidence))
            
            return {
                'predicted_probability': round(predicted_prob, 2),
                'confidence': round(confidence, 2),
                'reasoning': result.get('reasoning', ''),
                'key_factors': result.get('key_factors', []),
                'risk_factors': result.get('risk_factors', [])
            }
            
        except Exception as e:
            logger.error(f"AI prediction failed: {e}", exc_info=True)
            # 返回默认值
            return {
                'predicted_probability': current_market_prob,
                'confidence': 50.0,
                'reasoning': f'分析失败: {str(e)}',
                'key_factors': [],
                'risk_factors': []
            }
    
    def _calculate_opportunity_score(self, ai_prob: float, market_prob: float, 
                                     confidence: float) -> float:
        """
        计算机会评分（0-100）
        
        逻辑：
        - AI与市场差异越大，机会越好
        - 置信度越高，机会越好
        """
        divergence = abs(ai_prob - market_prob)
        # 差异越大，机会越好（最大40分）
        divergence_score = min(divergence * 2, 40)
        # 置信度越高，机会越好（最大60分）
        confidence_score = confidence * 0.6
        
        return round(divergence_score + confidence_score, 2)
    
    def _generate_recommendation(self, divergence: float, confidence: float) -> str:
        """
        生成推荐：YES/NO/HOLD
        
        逻辑：
        - AI概率 > 市场概率 + 5% 且置信度 > 60 → YES
        - AI概率 < 市场概率 - 5% 且置信度 > 60 → NO
        - 其他 → HOLD
        """
        if divergence > 5 and confidence > 60:
            return "YES"
        elif divergence < -5 and confidence > 60:
            return "NO"
        else:
            return "HOLD"
    
    def _assess_risk(self, market: Dict, ai_result: Dict) -> str:
        """评估风险等级"""
        confidence = ai_result.get('confidence', 50)
        divergence = abs(ai_result.get('predicted_probability', 50) - market.get('current_probability', 50))
        
        if confidence < 50 or divergence > 30:
            return "high"
        elif confidence < 70 or divergence > 15:
            return "medium"
        else:
            return "low"
    
    def _get_related_news(self, question: str) -> List[Dict]:
        """获取相关问题相关的新闻"""
        # 提取关键词
        keywords = self._extract_keywords(question)
        
        # 这里可以调用新闻API，暂时返回空列表
        # 实际实现时可以调用现有的新闻服务
        return []
    
    def _identify_related_assets(self, question: str) -> List[str]:
        """识别问题中提到的相关资产"""
        assets = []
        
        # 加密货币关键词映射
        crypto_keywords = {
            'BTC': ['BTC', 'Bitcoin', 'bitcoin', 'btc'],
            'ETH': ['ETH', 'Ethereum', 'ethereum', 'eth'],
            'SOL': ['SOL', 'Solana', 'solana', 'sol'],
            'BNB': ['BNB', 'Binance', 'binance', 'bnb'],
            'XRP': ['XRP', 'Ripple', 'ripple', 'xrp'],
            'ADA': ['ADA', 'Cardano', 'cardano', 'ada'],
            'DOGE': ['DOGE', 'Dogecoin', 'dogecoin', 'doge'],
            'AVAX': ['AVAX', 'Avalanche', 'avalanche', 'avax'],
            'DOT': ['DOT', 'Polkadot', 'polkadot', 'dot'],
            'MATIC': ['MATIC', 'Polygon', 'polygon', 'matic']
        }
        
        question_upper = question.upper()
        for symbol, keywords in crypto_keywords.items():
            if any(kw in question_upper for kw in keywords):
                assets.append(f"{symbol}/USDT")
        
        # 去重
        return list(set(assets))
    
    def _get_asset_data(self, assets: List[str]) -> Optional[Dict]:
        """获取资产数据（取第一个资产）"""
        if not assets:
            return None
        
        try:
            asset = assets[0]
            market_type = self._infer_market(asset)
            return self.data_collector.collect_all(
                market=market_type,
                symbol=asset,
                timeframe="1D"
            )
        except Exception as e:
            logger.debug(f"Failed to get asset data for {assets}: {e}")
            return None
    
    def _analyze_technical(self, asset_data: Dict) -> Dict:
        """简单的技术分析"""
        if not asset_data:
            return {
                'trend': 'neutral',
                'confidence': 50,
                'summary': '数据不足',
                'entry_suggestion': {}
            }
        
        indicators = asset_data.get('indicators', {})
        price_data = asset_data.get('price', {})
        
        # 简单的趋势判断
        rsi = indicators.get('rsi', {}).get('value', 50)
        macd_signal = indicators.get('macd', {}).get('signal', 'neutral')
        
        trend = 'neutral'
        if rsi > 60 and macd_signal == 'bullish':
            trend = 'bullish'
        elif rsi < 40 and macd_signal == 'bearish':
            trend = 'bearish'
        
        confidence = 60 if abs(rsi - 50) > 15 else 50
        
        return {
            'trend': trend,
            'confidence': confidence,
            'summary': f'RSI: {rsi:.1f}, MACD: {macd_signal}',
            'entry_suggestion': {}
        }
    
    def _infer_market(self, symbol: str) -> str:
        """推断市场类型"""
        if '/' in symbol:
            return "Crypto"
        elif len(symbol) <= 5 and symbol.isupper():
            return "USStock"
        else:
            return "Crypto"  # 默认
    
    def _extract_keywords(self, text: str) -> List[str]:
        """提取关键词"""
        # 简单的关键词提取
        words = re.findall(r'\b[A-Z][a-z]+\b|\b[A-Z]{2,}\b', text)
        return [w.lower() for w in words if len(w) > 2]
    
    def _get_cached_analysis(self, market_id: str, user_id: int = None) -> Optional[Dict]:
        """获取缓存的分析结果"""
        try:
            with get_db_connection() as db:
                cur = db.cursor()
                query = """
                    SELECT ai_predicted_probability, market_probability, divergence,
                           recommendation, confidence_score, opportunity_score,
                           reasoning, key_factors, related_assets, created_at
                    FROM qd_polymarket_ai_analysis
                    WHERE market_id = %s
                """
                params = [market_id]
                
                if user_id:
                    query += " AND user_id = %s"
                    params.append(user_id)
                else:
                    query += " AND user_id IS NULL"
                
                query += " ORDER BY created_at DESC LIMIT 1"
                
                cur.execute(query, params)
                row = cur.fetchone()
                cur.close()
                
                if row:
                    # RealDictCursor返回字典，使用键访问
                    key_factors_raw = row.get('key_factors')
                    key_factors = []
                    if key_factors_raw:
                        try:
                            if isinstance(key_factors_raw, str):
                                key_factors = json.loads(key_factors_raw)
                            else:
                                key_factors = key_factors_raw if isinstance(key_factors_raw, list) else []
                        except:
                            key_factors = []
                    
                    return {
                        "market_id": market_id,
                        "ai_predicted_probability": float(row.get('ai_predicted_probability') or 0),
                        "market_probability": float(row.get('market_probability') or 0),
                        "divergence": float(row.get('divergence') or 0),
                        "recommendation": row.get('recommendation') or 'HOLD',
                        "confidence_score": float(row.get('confidence_score') or 0),
                        "opportunity_score": float(row.get('opportunity_score') or 0),
                        "reasoning": row.get('reasoning') or '',
                        "key_factors": key_factors,
                        "related_assets": row.get('related_assets') if row.get('related_assets') else [],
                        "created_at": row.get('created_at')
                    }
        except Exception as e:
            logger.debug(f"Failed to get cached analysis: {e}")
        
        return None
    
    
    def _is_analysis_fresh(self, analysis: Dict, max_age_minutes: int = 30) -> bool:
        """检查分析结果是否新鲜"""
        created_at = analysis.get('created_at')
        if not created_at:
            return False
        
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        
        age = (datetime.now() - created_at.replace(tzinfo=None)).total_seconds() / 60
        return age < max_age_minutes
    
    def _save_analysis_to_db(self, analysis: Dict, user_id: int = None, language: str = 'en-US', model: str = None):
        """
        保存分析结果到数据库
        
        Args:
            analysis: 分析结果字典
            user_id: 用户ID
            language: 语言设置
            model: 使用的模型
        """
        try:
            with get_db_connection() as db:
                cur = db.cursor()
                
                # 1. 保存到 qd_polymarket_ai_analysis 表（Polymarket专用表）
                cur.execute("""
                    INSERT INTO qd_polymarket_ai_analysis
                    (market_id, user_id, ai_predicted_probability, market_probability,
                     divergence, recommendation, confidence_score, opportunity_score,
                     reasoning, key_factors, related_assets, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """, (
                    analysis['market_id'],
                    user_id,
                    analysis['ai_predicted_probability'],
                    analysis['market_probability'],
                    analysis['divergence'],
                    analysis['recommendation'],
                    analysis['confidence_score'],
                    analysis['opportunity_score'],
                    analysis['reasoning'],
                    json.dumps(analysis.get('key_factors', [])),
                    analysis.get('related_assets', [])
                ))
                
                # 2. 同时保存到 qd_analysis_tasks 表（用于管理员统计和统一的历史记录查看）
                market_info = analysis.get('market', {})
                market_title = market_info.get('question', '') or market_info.get('title', '') or f"Polymarket Market {analysis['market_id']}"
                result_json = json.dumps({
                    'market_id': analysis['market_id'],
                    'market_title': market_title,
                    'analysis': analysis,
                    'market': market_info,
                    'type': 'polymarket'  # 标记为Polymarket分析
                }, ensure_ascii=False)
                
                cur.execute("""
                    INSERT INTO qd_analysis_tasks
                    (user_id, market, symbol, model, language, status, result_json, error_message, created_at, completed_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                    RETURNING id
                """, (
                    int(user_id) if user_id else 1,
                    'Polymarket',  # market字段
                    str(analysis['market_id']),  # symbol字段存储market_id
                    str(model) if model else '',
                    str(language),
                    'completed',
                    result_json,
                    ''
                ))
                task_row = cur.fetchone()
                task_id = task_row['id'] if task_row else None
                
                db.commit()
                cur.close()
                
                if task_id:
                    logger.debug(f"Saved Polymarket analysis to both tables: task_id={task_id}, market_id={analysis['market_id']}")
        except Exception as e:
            logger.error(f"Failed to save analysis to DB: {e}")
    
    def _save_opportunities_to_db(self, market_id: str, opportunities: List[Dict]):
        """保存交易机会到数据库"""
        try:
            with get_db_connection() as db:
                cur = db.cursor()
                for opp in opportunities:
                    cur.execute("""
                        INSERT INTO qd_polymarket_asset_opportunities
                        (market_id, asset_symbol, asset_market, signal, confidence,
                         reasoning, entry_suggestion, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                    """, (
                        market_id,
                        opp['asset'],
                        opp['market'],
                        opp['signal'],
                        opp['confidence'],
                        opp['reasoning'],
                        json.dumps(opp.get('entry_suggestion', {}))
                    ))
                db.commit()
                cur.close()
        except Exception as e:
            logger.error(f"Failed to save opportunities to DB: {e}")
