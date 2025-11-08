#!/usr/bin/env python3
import ccxt.async_support as ccxt
import asyncio
import json
import os
import time
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from rich.console import Console
from rich.logging import RichHandler
from typing import Dict, List, Any
import traceback
import inspect
import random
from llm_integration import initialize_llm, get_trading_decision
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn

# Configuration
# NOTE: API keys are hardcoded here for illustration but should be moved to secure environment variables.
API_KEY = os.getenv('GATE_API_KEY', '4efbe203fbac0e4bcd0003a0910c801b')
API_SECRET = os.getenv('GATE_API_SECRET', '8b0e9cf47fdd97f2a42bca571a74105c53a5f906cd4ada125938d05115d063a0')
SYMBOL_FILE = 'symbols.json'
STATE_FILE = 'state.json'
TARGET_SYMBOLS = 9
TARGET_PNL_SEC = 0.01 # $0.60/min goal
MAX_RETRIES = 5
RETRY_DELAY = 0.1

def setup_logging():
    """Configure logging with both file and console handlers."""
    log_dir = 'logs'
    os.makedirs(log_dir, exist_ok=True)
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    formatter = logging.Formatter(log_format)
    log_file = os.path.join(log_dir, 'trading_bot.log')
    file_handler = RotatingFileHandler(
        log_file, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)

    console_handler = RichHandler(rich_tracebacks=True)
    # Note: Using the default RichHandler formatter for cleaner console output
    console_handler.setFormatter(logging.Formatter('%(message)s'))
    console_handler.setLevel(logging.DEBUG)

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logging.getLogger('ccxt').setLevel(logging.WARNING)
    logging.getLogger('asyncio').setLevel(logging.WARNING)
    return logger

# Setup logging
logger = setup_logging()
console = Console()

# ---------------- Genetic Algorithm (Stubs retained for context) ----------------
class GeneticOptimizer:
    def __init__(self, population_size=10, mutation_rate=0.2):
        self.population_size = population_size
        self.mutation_rate = mutation_rate
        self.population = []
        self.generation = 0
    # ... (Evolution logic is simplified/stubbed as it is outside the core PnL refactor scope) ...
    def init_population(self, base_config): self.population = [dict(base_config)] * self.population_size
    def fitness(self, config, pnl_rate, contrarian_bias): return pnl_rate * 1000 + contrarian_bias * 5
    def evolve(self, pnl_rate, contrarian_bias): return self.population[0] # Return best (stub)

# ---------------- Trading Bot (Refactored) ----------------
class TradingBot:
    def _log(self, level: str, message: str, **kwargs) -> None:
        """Custom logging function to include caller information and structured data."""
        frame = inspect.currentframe()
        # Navigate up to the actual calling function
        if frame is not None:
            # Use f_back twice to get the caller of the method containing _log
            caller_frame = frame.f_back.f_back
            if caller_frame is not None:
                caller = f"{os.path.basename(caller_frame.f_code.co_filename)}:{caller_frame.f_lineno}"
                log_data = {
                    'caller': caller,
                    'timestamp': datetime.utcnow().isoformat(),
                    'message': message,
                    **kwargs
                }
                getattr(logger, level.lower())(json.dumps(log_data, default=str))

    from exchange_manager import ExchangeManager

    def __init__(self, exchange_name='drift'):
        self._log('info', 'Initializing TradingBot instance')
        self.exchange = ExchangeManager(exchange_name)
        self.state = {}
        self.position_levels = {}
        self.llm = initialize_llm()
        self.running = False

        # --- NEW: Global PnL and Debt Tracking (Cartmanezonomics) ---
        self.global_pnl_memory = {
            'realized_profit': 0.0, # RP: Total profit from closed positive trades
            'total_subsidies_used': 0.0, # Total debt paid for subsidized exits
            'stuck_positions': {} # {unique_id: position_data} - Positions flagged for subsidized exit
        }
        self.stuck_positions_counter = 0 # Unique ID counter for stuck positions
        self.pair_health = {} # {symbol: PPS_score}

        self.config = {
            # Price range for coin selection
            "min_coin_price": 0.001,
            "max_coin_price": 0.01,

            # Position sizing and risk management
            "position_size_usd": 10,
            "max_position_size_usd": 20,
            "leverage": 1,

            # Trading parameters
            "profit_target_pct": 0.5,
            "stop_loss_pct": 0.25,
            "max_positions_per_symbol": 5,
            "position_spread_pct": 0.0001,

            # Order execution
            "offset": 0.00001,
            "loop_delay": 0.05,
            "monitor_interval": 5,

            # Error handling
            "max_retries": MAX_RETRIES,
            "retry_delay": 0.5,

            # Order size constraints
            "min_size": 0.001,
            "max_size": 0.1,

            # Precision settings
            "price_precision": 6,
            "amount_precision": 8,

            # --- NEW: Ticket Sizing and Targets ---
            # NOTE: These sizes MUST be properly scaled based on price to hit the desired $1/$10 notional
            # Assuming these are in base currency units for simplicity, they will be converted by ccxt.
            "initial_size_10c": 2.0, # Example size in base units (e.g. 100 units of a $0.05 coin = $5 notional)
            "initial_size_1c": 1.0,
            "profit_target_10c": 0.05, # $0.05 USD profit target for 10c tickets
            "profit_target_1c": 0.005, # $0.005 USD profit target for 1c tickets

            # --- NEW: PPS and Rotation Thresholds ---
            "pps_stuck_threshold": -5.0, # Lower value means tighter restriction on "stuck"
        }
        self._log('debug', 'Configuration loaded', config=self.config)

    # --- Utility Methods (Initialization, Logging, Sizing) ---

    async def initialize_exchange(self) -> None:
        """Initialize the exchange connection."""
        try:
            self._log('info', 'Initializing exchange connection')
            await self.exchange.initialize()
            # Fetch balance logic skipped for brevity, but retained in original code structure
        except Exception as e:
            self._log('error', 'Failed to initialize exchange', error=str(e))
            raise

    async def cleanup(self) -> None:
        """Clean up resources."""
        if self.exchange:
            try:
                await self.exchange.close()
                self.exchange = None # Reset exchange instance after closing
            except Exception as e:
                console.print(f"[red]Error during cleanup: {e}")

    async def calculate_order_size(self, symbol: str, size: float) -> float:
        """
        Calculate order size respecting minimums and precision.
        """
        # This will be delegated to the exchange manager
        return size

    # --- Position Management (Opening) ---

    async def open_position(self, symbol: str, side: str, amount: float) -> bool:
        """Opens a position, handling leverage, sizing, and limit order fill wait."""
        try:
            return await self.exchange.open_position(symbol, side, amount)
        except Exception as e:
            self._log('error', f'Error opening position for {symbol}', error=str(e))
            return False

    async def wait_for_fill(self, symbol: str, side: str, target_amount: float, timeout: int = 30) -> bool:
        """Wait for an order to fill."""
        # This logic will be moved to the exchange manager
        await asyncio.sleep(1) # Simulate a short delay
        return True

    async def raw_close_position(self, symbol: str, side: str, amount: float) -> bool:
        """
        Closes a position with a reduce-only limit order.
        """
        try:
            return await self.exchange.close_position(symbol, side, amount)
        except Exception as e:
            self._log('error', f'Error closing position for {symbol}', error=str(e))
            return False

    # --- PnL and Cartmanezonomics Logic (NEW) ---

    async def fetch_current_position_pnl(self, symbol: str, entry_price: float, amount: float, side: str) -> float:
        """Calculates the PnL of a single position based on current price (in USD)."""
        try:
            ticker = await self.exchange.fetch_ticker(symbol)
            current_price = float(ticker['last'])

            if side == 'long':
                pnl = (current_price - entry_price) * amount
            else: # 'short'
                pnl = (entry_price - current_price) * amount

            return pnl
        except Exception:
            self._log('error', f'Failed to calculate PnL for {symbol}', symbol=symbol)
            return 0.0

    async def close_position_smart(self, symbol: str, pos_data: Dict[str, Any]) -> bool:
        """
        Closes a.
        """
        current_pnl = await self.fetch_current_position_pnl(
            symbol, pos_data['entry'], pos_data['size'], pos_data['side']
        )
        amount = pos_data['size']
        side = pos_data['side']

        # 1. Standard PROFIT Exit
        if current_pnl >= 0.0: # Close at zero or better
            success = await self.raw_close_position(symbol, side, amount)
            if success:
                # Only add *positive* PnL to the RP bank
                self.global_pnl_memory['realized_profit'] += max(0, current_pnl)
                self._log('info', 'Standard PROFIT Exit', symbol=symbol, pnl=current_pnl)
            return success

        # 2. SUBSIDIZED LOSS Exit
        elif current_pnl < 0.0:
            subsidy_pnl = self.global_pnl_memory['realized_profit'] - self.global_pnl_memory['total_subsidies_used']
            trade_debt = abs(current_pnl)

            if subsidy_pnl >= trade_debt:
                success = await self.raw_close_position(symbol, side, amount)
                if success:
                    self.global_pnl_memory['total_subsidies_used'] += trade_debt
                    self._log('warning', 'SUBSIDIZED LOSS Exit', symbol=symbol,
                              debt_paid=trade_debt, remaining_subsidy=subsidy_pnl - trade_debt)
                return success
            else:
                self._log('debug', 'Cannot close red position - Insufficient Subsidy PnL', symbol=symbol)
                return False

        return False

    # --- Substitution Logic (NEW) ---

    async def get_pair_performance_score(self, symbol: str, current_positions: List[Dict]) -> float:
        """
        Calculate Pair Performance Score (PPS).
        Formula: Volume-based Liquidity/Volatility - Penalty for Locked Unrealized Loss.
        """
        try:
            ticker = await self.exchange.fetch_ticker(symbol)

            # 1. Volume/Liquidity (Proxy for action)
            volume_24h_usd = ticker.get('quoteVolume', 0)

            # 2. Open Debt Penalty (The Cost of Being Stuck)
            # Fetch unrealized PnL from the active positions
            unrealized_losses = sum(
                abs(float(p.get('unrealizedPnl', 0))) for p in current_positions if float(p.get('unrealizedPnl', 0)) < 0
            )

            # 3. Score Calculation (adjust multipliers based on testing)
            # High volume is good (e.g., $10k/day = 1.0 point), $1 of loss is -5 points.
            pps_score = (volume_24h_usd / 10000.0) - (unrealized_losses * 5.0)

            self.pair_health[symbol] = pps_score
            return pps_score
        except Exception:
            self._log('error', f'Failed to calculate PPS for {symbol}', symbol=symbol)
            return -999.0 # Effectively force freezing if data retrieval fails

    async def fetch_eligible_symbols(self) -> List[str]:
        """
        Fetch and filter symbols based on price, returning a list of eligible symbols.
        """
        try:
            return await self.exchange.fetch_eligible_symbols(self.config)
        except Exception as e:
            self._log('error', 'Failed to fetch or filter symbols', error=str(e))
            return []

    # --- Main Loops ---

    async def run_bot(self) -> None:
        """Main bot execution loop."""
        self.running = True
        # ... (initialization and symbol fetching logic remains the same) ...
        # Simplified for brevity, assuming successful initialization

        await self.initialize_exchange()

        symbols_data = await self.fetch_eligible_symbols()
        symbols = [d['symbol'] for d in symbols_data]


        if not symbols:
            self._log('error', 'No eligible trading symbols found.')
            return

        self._log('info', f'Starting trading with {len(symbols)} symbols', symbols=symbols)

        monitor_task = asyncio.create_task(self.monitor_loop(symbols))

        try:
            tasks = [asyncio.create_task(self.trade_loop(symbol), name=f'trade_loop_{symbol}') for symbol in symbols]
            await asyncio.gather(*tasks, return_exceptions=True)

        except Exception as e:
            self._log('critical', 'Fatal error in main loop', error=str(e))
        finally:
            if not monitor_task.done(): monitor_task.cancel()
            await self.cleanup()

    async def trade_loop(self, symbol: str) -> None:
        """Main trading loop for a single symbol."""
        while self.running:
            try:
                await self.execute_trades(symbol)
            except Exception as e:
                self._log('error', f'Error in trade loop', symbol=symbol, error=str(e))
            finally:
                # Use faster loop_delay for high-frequency checks
                await asyncio.sleep(self.config['loop_delay'])

    async def execute_trades(self, symbol: str) -> None:
        """Execute DCA trading strategy with PPS-based substitution logic."""
        await self.initialize_exchange()

        # Initialize tracking for the symbol
        if symbol not in self.position_levels:
            self.position_levels[symbol] = {
                'long_positions': [],
                'short_positions': [],
                'last_trade_time': 0
            }

        try:
            current_time = time.time()
            positions = await self.exchange.fetch_positions([symbol], {'type': 'swap'})

            # --- 1. PERFORMANCE CHECK (Substitution Logic) ---
            pps = await self.get_pair_performance_score(symbol, positions)
            is_stuck_and_red = pps < self.config['pps_stuck_threshold']

            if is_stuck_and_red:
                # If stuck, check existing positions for debt and park them.
                for position in positions:
                    unrealized_pnl = float(position.get('unrealizedPnl', 0))
                    if unrealized_pnl < 0:
                        unique_id = f"{symbol}_{self.stuck_positions_counter}"
                        self.stuck_positions_counter += 1

                        # Store debt in the global memory for subsidized exit
                        self.global_pnl_memory['stuck_positions'][unique_id] = {
                            'symbol': symbol,
                            'side': position['side'],
                            'size': float(position['contracts']),
                            'entry': float(position['entryPrice']),
                            'id': unique_id
                        }
                        self._log('debug', 'Position debt parked', id=unique_id, symbol=symbol)

                # Skip new entry logic
                return

            # --- 2. TAKE-PROFIT LOGIC (Standard Exits) ---

            # The current CCXT API fetch_positions is used to iterate over actual open positions.
            for position in positions:
                if float(position['contracts']) <= 0: continue

                side = position['side']
                amount = float(position['contracts'])
                entry = float(position['entryPrice'])

                # Using 10c target as a proxy TP for any position
                if float(position.get('unrealizedPnl', 0)) >= self.config['profit_target_10c']:

                    pos_data = {'symbol': symbol, 'side': side, 'size': amount, 'entry': entry}
                    await self.close_position_smart(symbol, pos_data)

            # --- 3. NEW ENTRY LOGIC (DCA Pipelining) ---

            # LLM-driven decision making
            prompt = f"The current market trend for {symbol} is [placeholder_trend]. The bot's current PnL is {self.state.get(symbol, 0)}. Should I long, short, or hold?"
            decision = get_trading_decision(self.llm, prompt)
            self._log('info', f"LLM decision for {symbol}: {decision}")

            # Only proceed with trades if the LLM gives a clear signal
            if "long" not in decision.lower() and "short" not in decision.lower():
                return

            max_positions = self.config['max_positions_per_symbol']

            # Calculate actual position count from the active exchange positions
            active_long_count = sum(1 for p in positions if p['side'] == 'long' and float(p['contracts']) > 0)
            active_short_count = sum(1 for p in positions if p['side'] == 'short' and float(p['contracts']) > 0)

            if (current_time - self.position_levels[symbol]['last_trade_time']) > 0.5: # Faster 0.5 sec cooldown
                # Open 10c (larger) long position
                if active_long_count < max_positions // 2:
                    size = self.config['initial_size_10c']
                    if await self.open_position(symbol, 'buy', size):
                        self.position_levels[symbol]['last_trade_time'] = current_time

                # Open 1c (smaller) long position
                if active_long_count < max_positions:
                    size = self.config['initial_size_1c']
                    if await self.open_position(symbol, 'buy', size):
                        self.position_levels[symbol]['last_trade_time'] = current_time

                # Open 10c (larger) short position
                if active_short_count < max_positions // 2:
                    size = self.config['initial_size_10c']
                    if await self.open_position(symbol, 'sell', size):
                        self.position_levels[symbol]['last_trade_time'] = current_time

                # Open 1c (smaller) short position
                if active_short_count < max_positions:
                    size = self.config['initial_size_1c']
                    if await self.open_position(symbol, 'sell', size):
                        self.position_levels[symbol]['last_trade_time'] = current_time

            # Update symbol PnL state
            self.state[symbol] = sum(float(p.get('realizedPnl', 0)) + float(p.get('unrealizedPnl', 0)) for p in positions)

        except Exception as e:
            self._log('error', f'Error in execute_trades', symbol=symbol, error=str(e), traceback=traceback.format_exc())


    async def monitor_loop(self, symbols: List[str]) -> None:
        """Monitor, adjust parameters, and orchestrate subsidized exits (Trade Debt Allocator)."""
        start_time = time.time()
        while self.running:
            try:
                total_pnl = sum(self.state.values())
                elapsed = max(time.time() - start_time, 1)
                rate = total_pnl / elapsed

                # --- Cartmanezonomics Status ---
                rp = self.global_pnl_memory['realized_profit']
                subsidy_used = self.global_pnl_memory['total_subsidies_used']
                subsidy_pnl = rp - subsidy_used # Subsidy PnL Bank
                stuck_count = len(self.global_pnl_memory['stuck_positions'])

                console.print(
                    f"[bold green]PnL: ${total_pnl:.4f} | "
                    f"Rate: ${rate * 60:.3f}/min | " # Display in $/min
                    f"Subsidy Bank: ${subsidy_pnl:.4f} | "
                    f"Stuck Debt: {stuck_count}"
                )

                # --- Trade Debt Allocation (Attempt Subsidized Exit) ---
                closed_count = 0
                keys_to_delete = []

                # Iterate through debt pool and try to clear it using the PnL Bank
                for key, pos_data in list(self.global_pnl_memory['stuck_positions'].items()):
                    if await self.close_position_smart(pos_data['symbol'], pos_data):
                        keys_to_delete.append(key)
                        closed_count += 1

                for key in keys_to_delete:
                    del self.global_pnl_memory['stuck_positions'][key]

                if closed_count > 0:
                    self._log('info', f'Cleared {closed_count} stuck debts using PnL Bank.', closed_count=closed_count)

                # --- Genetic/Scaling Adjustment Logic (Simplified) ---
                target_rate = TARGET_PNL_SEC # $0.01/sec = $0.60/min
                if elapsed > 300: # Adjust after 5 minutes of stability
                    size_adjustment = 1.0 + min(0.5, max(-0.5, (rate - target_rate) / target_rate * 0.1))

                    new_10c_size = self.config['initial_size_10c'] * size_adjustment
                    self.config['initial_size_10c'] = min(self.config['max_size'] * 1000, max(self.config['min_size'], new_10c_size))
                    self.config['initial_size_1c'] = self.config['initial_size_10c'] * 0.1

            except Exception as e:
                self._log('error', f'Monitor error', error=str(e), traceback=traceback.format_exc())

            await asyncio.sleep(self.config['monitor_interval'])

app = FastAPI()
bot = TradingBot(exchange_name='drift')

# Serve the frontend
app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")

@app.get("/")
async def read_index():
    return FileResponse('frontend/index.html')

@app.get("/status")
async def get_status():
    return {
        "running": bot.running,
        "pnl": bot.global_pnl_memory,
        "positions": bot.position_levels,
        "pair_health": bot.pair_health
    }

@app.post("/start")
async def start_bot():
    if not bot.running:
        asyncio.create_task(bot.run_bot())
        return {"status": "Bot started"}
    return {"status": "Bot is already running"}

@app.post("/stop")
async def stop_bot():
    if bot.running:
        bot.running = False
        return {"status": "Bot stopped"}
    return {"status": "Bot is not running"}

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--exchange', type=str, default='drift', help='The exchange to trade on (drift or hyperliquid)')
    args = parser.parse_args()

    # The bot is now controlled via the API, not started automatically
    uvicorn.run(app, host="0.0.0.0", port=8000)
