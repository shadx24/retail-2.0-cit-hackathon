#!/usr/bin/env python3
"""
Agent Engine — Main entrypoint for the Goal-Oriented Autonomous Web Agent.

Replaces the deterministic engine.py with an LLM-driven reasoning loop:
  Observe → Reason → Act → Evaluate → Update Memory → Repeat

Usage:
  python3 agent_engine.py           # Run for default shop (ID: 1)
  python3 agent_engine.py 1         # Run for shop ID 1
  python3 agent_engine.py 2         # Run for shop ID 2
  python3 agent_engine.py --shop 3  # Run for shop ID 3
"""
import asyncio
import random
import time
import traceback
import gc
import sys
import os
from datetime import datetime

from config import Timing
from database import SupabaseStore
from agent_core import AgentReasoningCore
from price_intelligence import PriceIntelligenceEngine, print_pricing_report


class AgentExecutionController:
    """
    Top-level execution controller for the web agent.
    Manages the agent lifecycle with safety guardrails.
    Supports multi-tenant operation via shop_id parameter.
    """

    def __init__(self, shop_id: int = 1):
        self.db = SupabaseStore()
        self.shop_id = shop_id
        self.agent = AgentReasoningCore(self.db, shop_id=shop_id)
        self.price_engine = PriceIntelligenceEngine(self.db, margin_percent=1.0)
        self._running = False
        self._start_time = datetime.utcnow()
        self._total_cycles = 0
        self._total_prices = 0
        self._pricing_report_interval = 10  # Generate report every 10 cycles

    async def initialize(self):
        """Seed keywords and prepare agent for the shop."""
        print("=" * 80)
        print("  GOAL-ORIENTED AUTONOMOUS WEB AGENT")
        print("  Objective: Monitor competitor prices and pricing trends")
        print("  Model: moonshotai/kimi-k2-instruct (NVIDIA)")
        print(f"  Shop ID: {self.shop_id}")
        print("=" * 80)
        print()

        print("[AgentEngine] Initializing database...")
        await self.db.initialize_keyword_pool()
        print("[AgentEngine] Ready.\n")

    async def run_forever(self):
        """Main agent loop."""
        await self.initialize()
        self._running = True

        while self._running:
            try:
                # Run one agent cycle
                summary = await self.agent.run_cycle()
                self._total_cycles += 1
                self._total_prices += summary.get("prices_found", 0)

                # Print cumulative stats
                runtime = datetime.utcnow() - self._start_time
                print(f"\n[AgentEngine] Cumulative: {self._total_cycles} cycles, "
                      f"{self._total_prices} prices, runtime: {runtime}")

                # Generate pricing report every N cycles
                if self._total_cycles % self._pricing_report_interval == 0:
                    print("\n" + "=" * 80)
                    print("[AgentEngine] Generating pricing intelligence report...")
                    print("=" * 80)
                    await print_pricing_report(self.db)

                # Randomized sleep between cycles (shorter than deterministic engine)
                sleep_minutes = random.randint(
                    max(1, Timing.CYCLE_MIN_SLEEP // 3),
                    max(2, Timing.CYCLE_MAX_SLEEP // 3),
                )
                print(f"[AgentEngine] Sleeping {sleep_minutes} minutes...\n")

                for _ in range(sleep_minutes * 6):  # 10s chunks
                    if not self._running:
                        break
                    await asyncio.sleep(10)

                gc.collect()

            except KeyboardInterrupt:
                print("\n[AgentEngine] Interrupted by user")
                break
            except Exception as e:
                print(f"[AgentEngine] Critical error: {e}")
                traceback.print_exc()
                await asyncio.sleep(60)

        await self.shutdown()

    async def run_single_cycle(self):
        """Run just one cycle (for testing)."""
        await self.initialize()
        summary = await self.agent.run_cycle()
        await self.shutdown()
        return summary

    def stop(self):
        self._running = False

    async def shutdown(self):
        """Clean shutdown."""
        print("[AgentEngine] Shutting down...")
        await self.agent.shutdown()

        runtime = datetime.utcnow() - self._start_time
        print(f"[AgentEngine] Total cycles: {self._total_cycles}")
        print(f"[AgentEngine] Total prices: {self._total_prices}")
        print(f"[AgentEngine] Runtime: {runtime}")
        print("[AgentEngine] Shutdown complete")


def run(shop_id: int = 1):
    """Entry point. Run agent for specified shop."""
    controller = AgentExecutionController(shop_id=shop_id)
    try:
        asyncio.run(controller.run_forever())
    except Exception as e:
        print(f"Fatal error: {e}")
        traceback.print_exc()


def run_once(shop_id: int = 1):
    """Run a single cycle for testing."""
    controller = AgentExecutionController(shop_id=shop_id)
    try:
        return asyncio.run(controller.run_single_cycle())
    except Exception as e:
        print(f"Fatal error: {e}")
        traceback.print_exc()


def parse_shop_id():
    """Parse shop_id from command line or environment."""
    # Check for environment variable
    if "AGENT_SHOP_ID" in os.environ:
        return int(os.environ["AGENT_SHOP_ID"])
    
    # Check for command line args
    if len(sys.argv) > 1:
        try:
            return int(sys.argv[1])
        except ValueError:
            if sys.argv[1].startswith("--shop"):
                return int(sys.argv[1].split("=")[1])
    
    # Default
    return 1


if __name__ == "__main__":
    shop_id = parse_shop_id()
    print(f"[AgentEngine] Starting with shop_id={shop_id}")
    run(shop_id=shop_id)
