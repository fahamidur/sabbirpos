from flask import Flask, request, redirect, url_for, render_template_string, flash, get_flashed_messages
import threading
import time
import os
import requests
import hmac
import hashlib
import base64
import json

app = Flask(__name__)
app.secret_key = 'your_secret_key'

bot_running = False
log_history = []
lock = threading.Lock()
stop_event = threading.Event()
pause_new_trades = False
active_trades = 0
enabled_filters = set(range(4))
divergence_lookback = 20
minflex = 2
take_profit_percent = 5
stop_loss_percent = 3
last_scan_asset = ""
last_scan_tf = ""
last_signal = ""
last_trade = ""

timeframe = os.getenv("TIMEFRAME", "1h")
risk = float(os.getenv("RISK", "5"))
okx_api_key = os.getenv("OKX_API_KEY", "fd15e419-0838-4b1e-9ddd-6212294f765e")
okx_api_secret = os.getenv("OKX_API_SECRET", "9DF900F8E676B4110F6A4A1305CED7F2")
okx_api_passphrase = os.getenv("OKX_API_PASSPHRASE", "BlackPlatypus10$")

active_assets = {"BTC-USDT": True, "ETH-USDT": True}
asset_risks = {"BTC-USDT": risk, "ETH-USDT": risk}

# ...existing code...
DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RSI Divergence Bot</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            background-color: #111827;
            color: white;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            min-height: 100vh;
            padding: 24px;
        }

        .container {
            max-width: 1152px;
            margin: 0 auto;
        }

        h1 {
            font-size: 2.25rem;
            font-weight: bold;
            margin-bottom: 32px;
        }

        .grid {
            display: grid;
            gap: 24px;
        }

        .grid-2 {
            grid-template-columns: 1fr 1fr;
        }

        .card {
            background-color: #1f2937;
            border-radius: 8px;
            padding: 24px;
        }

        .card h2 {
            font-size: 1.5rem;
            font-weight: 600;
            margin-bottom: 24px;
        }

        .status-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 24px;
            margin-bottom: 24px;
        }

        .status-item {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .status-label {
            color: #d1d5db;
        }

        .status-value {
            color: white;
        }

        .button-group {
            display: flex;
            gap: 16px;
        }

        .btn {
            background-color: #059669;
            color: white;
            padding: 12px 24px;
            border-radius: 8px;
            border: none;
            font-weight: 500;
            cursor: pointer;
            transition: background-color 0.2s;
        }

        .btn:hover {
            background-color: #047857;
        }

        .actions-list {
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        .action-item {
            font-size: 0.875rem;
        }

        .action-time {
            color: #9ca3af;
            margin-bottom: 4px;
        }

        .action-text {
            color: white;
            margin-bottom: 4px;
        }

        .settings-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 32px;
        }

        .settings-section {
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        .setting-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .setting-label {
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .checkbox {
            width: 20px;
            height: 20px;
            accent-color: #10b981;
        }

        .slider {
            width: 96px;
            height: 8px;
            background: #4b5563;
            border-radius: 4px;
            appearance: none;
            cursor: pointer;
        }

        .slider::-webkit-slider-thumb {
            -webkit-appearance: none;
            appearance: none;
            width: 18px;
            height: 18px;
            border-radius: 50%;
            background: #10b981;
            cursor: pointer;
        }

        .slider::-moz-range-thumb {
            width: 18px;
            height: 18px;
            border-radius: 50%;
            background: #10b981;
            cursor: pointer;
            border: none;
        }

        .section-title {
            font-weight: 500;
            margin-top: 24px;
            margin-bottom: 12px;
        }

        .mt-6 {
            margin-top: 24px;
        }

        @media (max-width: 1024px) {
            .grid-2 {
                grid-template-columns: 1fr;
            }
            
            .settings-grid {
                grid-template-columns: 1fr;
            }
        }

        @media (max-width: 768px) {
            body {
                padding: 16px;
            }
            
            h1 {
                font-size: 1.875rem;
            }
            
            .status-grid {
                grid-template-columns: 1fr;
            }
            
            .button-group {
                flex-direction: column;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <h1>RSI Divergence Bot</h1>
        
        <div class="grid grid-2">
            <!-- Live Bot Status -->
            <div class="card">
                <h2>Live Bot Status</h2>
                
                <div class="status-grid">
                    <div class="status-item">
                        <div class="status-label">Last Scanned:</div>
                        <div class="status-value">BTC-USDT on 1h</div>
                    </div>
                    <div class="status-item">
                        <div class="status-label">Last Signal:</div>
                        <div class="status-value">Bullish</div>
                    </div>
                    <div class="status-item">
                        <div class="status-label">Last Signal</div>
                        <div class="status-value">BTC-USDT Sell</div>
                    </div>
                </div>
                
                <div class="button-group">
                    <button class="btn">Start Bot</button>
                    <button class="btn">Stop Bot</button>
                </div>
            </div>

            <!-- Recent Actions -->
            <div class="card">
                <h2>Recent Actions</h2>
                
                <div class="actions-list">
                    <div class="action-item">
                        <div class="action-time">[2025-05-24 03:04:25 03:05</div>
                        <div class="action-text">Scanning ETH-USDT on th...</div>
                        <div class="action-text">Scanning BTC-USDT</div>
                        <div class="action-text">Actual bullish divergence detected</div>
                    </div>
                    
                    <div class="action-item">
                        <div class="action-time">[2025-05-24 03:04:34 03:05</div>
                        <div class="action-text">Scanning ETH-USDT on 1 h...</div>
                        <div class="action-text">Actual bullish divergence detected</div>
                    </div>
                    
                    <div class="action-item">
                        <div class="action-time">[2025-05-24 03:04:24 03:05</div>
                        <div class="action-text">Executing real trade</div>
                    </div>
                    
                    <div class="action-item">
                        <div class="action-time">[2025-05-24 03:04:25 03:05</div>
                        <div class="action-text">Scanning ETH-USDT on th...</div>
                        <div class="action-text">Executing real trade</div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Bot Settings -->
        <div class="card mt-6">
            <h2>Bot Settings</h2>
            
            <div class="settings-grid">
                <!-- Left Column -->
                <div class="settings-section">
                    <div class="setting-item">
                        <div class="setting-label">
                            <input type="checkbox" class="checkbox" checked>
                            <span>Risk (%)</span>
                        </div>
                        <span>5</span>
                    </div>
                    
                    <div class="setting-item">
                        <div class="setting-label">
                            <input type="checkbox" class="checkbox" checked>
                            <span>Timeframes</span>
                        </div>
                        <input type="range" class="slider" value="50">
                    </div>
                    
                    <div class="setting-item">
                        <div class="setting-label">
                            <input type="checkbox" class="checkbox" checked>
                            <span>MinFlex</span>
                        </div>
                        <span>2</span>
                    </div>
                    
                    <div class="setting-item">
                        <div class="setting-label">
                            <input type="checkbox" class="checkbox" checked>
                            <span>Divergence Lookback</span>
                        </div>
                    </div>
                    
                    <h3 class="section-title">Filter Toggles</h3>
                    
                    <div class="settings-section">
                        <div class="setting-item">
                            <div class="setting-label">
                                <input type="checkbox" class="checkbox" checked>
                                <span>News Auto-Pause</span>
                            </div>
                        </div>
                        
                        <div class="setting-item">
                            <div class="setting-label">
                                <input type="checkbox" class="checkbox" checked>
                                <span>RSI Overbought/Oversold Zones</span>
                            </div>
                        </div>
                        
                        <div class="setting-item">
                            <div class="setting-label">
                                <input type="checkbox" class="checkbox" checked>
                                <span>Divergence Strength</span>
                            </div>
                        </div>
                        
                        <div class="setting-item">
                            <div class="setting-label">
                                <input type="checkbox" class="checkbox" checked>
                                <span>RSI Slope</span>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Right Column -->
                <div class="settings-section">
                    <div class="setting-item">
                        <span>Filter Toggles</span>
                        <input type="range" class="slider" value="70">
                    </div>
                    
                    <h3 class="section-title">Assets</h3>
                    
                    <div class="settings-section">
                        <div class="setting-item">
                            <div class="setting-label">
                                <input type="checkbox" class="checkbox" checked>
                                <span>BTC-USDT</span>
                            </div>
                            <span>55%</span>
                        </div>
                        
                        <div class="setting-item">
                            <div class="setting-label">
                                <input type="checkbox" class="checkbox" checked>
                                <span>ETH-USDT</span>
                            </div>
                            <span>5,0%</span>
                        </div>
                        
                        <div class="setting-item">
                            <div class="setting-label">
                                <input type="checkbox" class="checkbox">
                                <span>ETH-USDT Risk</span>
                            </div>
                            <span>50%</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
"""
# ...existing code...

def log(message):
    global log_history
    with lock:
        timestamp = time.strftime("[%Y-%m-%d %H:%M:%S]")
        log_history.insert(0, f"{timestamp} {message}")
        log_history = log_history[:100]

def fetch_okx_balance():
    url = "https://www.okx.com/api/v5/account/balance"
    request_path = "/api/v5/account/balance"
    query_string = "ccy=USDT"
    method = "GET"
    body = ""
    timestamp = time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime()) + ".000Z"
    message = f"{timestamp}{method}{request_path}?{query_string}{body}"
    try:
        signature = base64.b64encode(
            hmac.new(
                okx_api_secret.encode('utf-8'),
                message.encode('utf-8'),
                hashlib.sha256
            ).digest()
        ).decode()
    except Exception as e:
        log(f"Error encoding signature: {e}")
        return 0

    headers = {
        'OK-ACCESS-KEY': okx_api_key,
        'OK-ACCESS-SIGN': signature,
        'OK-ACCESS-TIMESTAMP': timestamp,
        'OK-ACCESS-PASSPHRASE': okx_api_passphrase
    }

    try:
        response = requests.get(url, headers=headers, params={"ccy": "USDT"})
        log(f"Fetching balance for USDT...")
        if response.status_code == 200:
            data = response.json()
            total_eq = data['data'][0].get('totalEq', None)
            if total_eq is not None:
                return float(total_eq)
            else:
                log("totalEq not found in response.")
                return 0
        else:
            log(f"Error fetching balance: {response.status_code} - {response.text}")
    except Exception as e:
        log(f"Error fetching balance: {e}")
    return 0

def get_price_data(symbol, tf, limit):
    try:
        url = "https://www.okx.com/api/v5/market/candles"
        tf_okx = tf.upper()
        r = requests.get(url, params={"instId": symbol, "bar": tf_okx, "limit": limit})
        if r.status_code == 200:
            data = r.json()
            if "data" in data and len(data["data"]) > 0:
                closes = [float(c[4]) for c in reversed(data["data"])]
                return closes
        else:
            log(f"Failed to get prices: {r.text}")
    except Exception as e:
        log(f"Price data error: {e}")
    return []

def calculate_rsi(prices, period=14):
    if len(prices) < period + 1: return []
    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gains = [max(0, d) for d in deltas]
    losses = [abs(min(0, d)) for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    rsis = []
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        rs = avg_gain / avg_loss if avg_loss != 0 else 0
        rsis.append(100 - 100 / (1 + rs))
    return rsis

def find_divergence(prices, rsis, lookback=divergence_lookback):
    min_len = min(len(prices), len(rsis))
    prices = prices[-min_len:]
    rsis = rsis[-min_len:]
    if min_len < lookback:
        log(f"[DEBUG] Skipped: Not enough aligned data (have {min_len}, need {lookback})")
        return None

    recent_prices = prices[-lookback:]
    recent_rsis = rsis[-lookback:]

    price_low = min(recent_prices)
    rsi_low = min(recent_rsis)
    price_high = max(recent_prices)
    rsi_high = max(recent_rsis)
    price_now = prices[-1]
    rsi_now = rsis[-1]

    if price_now < price_low and rsi_now > rsi_low:
        log("** ACTUAL BULLISH DIVERGENCE DETECTED **")
        return "bullish"
    if price_now > price_high and rsi_now < rsi_high:
        log("** ACTUAL BEARISH DIVERGENCE DETECTED **")
        return "bearish"
    return None

def apply_filters(symbol, side):
    mandatory = [0, 1, 2, 3]
    passed_mandatory = all(f in enabled_filters for f in mandatory if f in enabled_filters)
    if not passed_mandatory:
        log(f"[FILTER] Mandatory filters FAILED for {symbol} ({side})")
        return False

    optional = [i for i in range(4, 15)]
    enabled_flex = [f for f in optional if f in enabled_filters]
    passed = len(enabled_flex)

    if len(enabled_flex) == 0:
        log(f"[FILTER] No flexible filters enabled, skipping MinFlex check.")
        return True

    if passed < minflex:
        log(f"[FILTER] Flexible filters FAILED for {symbol} ({side}): {passed}/{len(enabled_flex)} < MinFlex={minflex}")
        return False

    log(f"[FILTER] All filters passed for {symbol} ({side})")
    return True

def calculate_quantity(symbol, price):
    balance = fetch_okx_balance()
    if balance <= 0: return 0
    return round((balance * asset_risks[symbol] / 100) / price, 8)

def place_real_order(symbol, side, qty):
    try:
        url = "https://www.okx.com/api/v5/trade/order"
        ts = time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime()) + ".000Z"
        body = json.dumps({
            "instId": symbol,
            "side": side,
            "ordType": "market",
            "sz": f"{qty:.8f}".rstrip('0').rstrip('.')
        })
        msg = f"{ts}POST/api/v5/trade/order{body}"
        sig = base64.b64encode(hmac.new(okx_api_secret.encode(), msg.encode(), hashlib.sha256).digest()).decode()
        headers = {
            'OK-ACCESS-KEY': okx_api_key,
            'OK-ACCESS-SIGN': sig,
            'OK-ACCESS-TIMESTAMP': ts,
            'OK-ACCESS-PASSPHRASE': okx_api_passphrase,
            'Content-Type': 'application/json'
        }
        r = requests.post(url, headers=headers, data=body)
        log(f"Order Response: {r.text}")
    except Exception as e:
        log(f"Order Error: {e}")

def execute_trade(symbol, side):
    global last_trade
    required = divergence_lookback + 14
    prices = get_price_data(symbol, "1m", required)
    rsis = calculate_rsi(prices)
    if not prices or not rsis:
        log(f"[TRADE] Not enough data for {symbol} ({side}) - skipping")
        return
    qty = calculate_quantity(symbol, prices[-1])
    if qty <= 0:
        log(f"[TRADE] Invalid quantity for {symbol} ({side}) - skipping")
        return
    log(f"=== EXECUTING REAL TRADE: {symbol} {side.upper()} ===")
    place_real_order(symbol, side, qty)
    last_trade = f"{symbol} {side.upper()}"

def bot_task():
    global bot_running, last_scan_asset, last_scan_tf, last_signal
    log("Bot is now actively monitoring assets...")
    while bot_running:
        for tf in timeframe.split(','):
            for sym in active_assets:
                if not active_assets[sym] or pause_new_trades:
                    continue

                log(f"Scanning {sym} on {tf}...")
                last_scan_asset = sym
                last_scan_tf = tf

                required = divergence_lookback + 15
                prices = get_price_data(sym, tf, required)
                rsis = calculate_rsi(prices)

                signal = find_divergence(prices[-len(rsis):], rsis)
                last_signal = signal or "none"
                log(f"{sym} | {tf} | signal: {signal}")

                if signal and apply_filters(sym, "buy" if signal == "bullish" else "sell"):
                    execute_trade(sym, "buy" if signal == "bullish" else "sell")

        if stop_event.wait(60):
            break

@app.route('/')
def dashboard():
    balance = fetch_okx_balance()
    return render_template_string(
        DASHBOARD_TEMPLATE,
        running=bot_running,
        log=log_history,
        risk=risk,
        timeframe=timeframe,
        minflex=minflex,
        pause_new_trades=pause_new_trades,
        active_assets=active_assets,
        asset_risks=asset_risks,
        active_trades=active_trades,
        usdt_balance=f"{balance:.2f}",
        aud_balance=f"{balance*1.5:.2f}",
        messages=get_flashed_messages(),
        enabled_filters=enabled_filters,
        divergence_lookback=divergence_lookback,
        last_scan_asset=last_scan_asset,
        last_scan_tf=last_scan_tf,
        last_signal=last_signal,
        last_trade=last_trade
    )

@app.route('/start', methods=['POST'])
def start():
    global bot_running
    bot_running = True
    stop_event.clear()
    threading.Thread(target=bot_task).start()
    log("Bot started.")
    return redirect(url_for('dashboard'))

@app.route('/force_trade', methods=['POST'])
def force_trade():
    symbol = request.form.get('symbol', 'BTC-USDT')
    direction = request.form.get('direction', 'buy')
    log(f"=== FORCING {direction.upper()} TRADE on {symbol} ===")
    execute_trade(symbol, direction)
    return redirect(url_for('dashboard'))

@app.route('/stop', methods=['POST'])
def stop():
    global bot_running
    bot_running = False
    stop_event.set()
    log("Bot stopped.")
    return redirect(url_for('dashboard'))

@app.route('/update', methods=['POST'])
def update_settings():
    global risk, timeframe, minflex, pause_new_trades, active_assets, asset_risks, enabled_filters, divergence_lookback
    try:
        risk = float(request.form.get('risk', risk))
        timeframe = request.form.get('timeframe', timeframe)
        minflex = int(request.form.get('minflex', minflex))
        divergence_lookback = int(request.form.get('lookback', divergence_lookback))
        pause_new_trades = 'pause_new_trades' in request.form
        enabled_filters = set(map(int, request.form.getlist('filters')))
        for s in active_assets:
            active_assets[s] = s in request.form.getlist('assets')
            asset_risks[s] = float(request.form.get(f"risk_{s}", asset_risks[s]))
        log(f"Settings updated. Filters: {enabled_filters}")
    except Exception as e:
        log(f"Error updating settings: {e}")
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)