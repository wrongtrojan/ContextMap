import os
import asyncio
import logging
import json
import httpx
import time
from core.tools_manager import ToolsManager
from core.system_state import SystemStateManager,SystemStatus
from core.prompts_manager import PromptManager
from dotenv import load_dotenv

logger = logging.getLogger("IngestionStream")
load_dotenv()

class IngestionStream:
    def __init__(self, tools_manager: ToolsManager):
        self.tools = tools_manager
        self.state_manager = SystemStateManager()
        self.prompt_manager = PromptManager()
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        self.api_url = "https://api.deepseek.com/v1/chat/completions"

    async def run_global_sync(self):
        """
        🎬 [Global Sync] 
        """
        try:
            start_time = time.time()
            self.state_manager.reset_progress()
            self.state_manager.update_progress("Global", 0, "Initiating global sync...")
            logger.info("🎬 [START] Global ingestion sync initiated.")

            await self._drive_raw_processing_suite()

            logger.info("🔎 [Messenger] Scanning storage for incremental assets...")
            scan_res = await asyncio.to_thread(self.tools.call_messenger_come)
            
            pending_tasks = scan_res.get("tasks", [])
            if not pending_tasks:
                logger.info("✨ [Finished] No new content found. System is up-to-date.")
                return

            logger.info(f"📦 [Discovery] Found {len(pending_tasks)} new items awaiting AI synthesis.")

            self.state_manager.set_active_assets([task["asset_id"] for task in pending_tasks])
            total_pending = len(pending_tasks)

            for i, task in enumerate(pending_tasks):
                asset_id = task["asset_id"]
                asset_type = task["asset_type"]
                context = task["context"]

                try:
                    current_pct = int(((i + 1) / total_pending) * 100)
                    self.state_manager.update_progress(
                        "AI-Synthesis", 
                        current_pct, 
                        f"Processing {asset_type}: {asset_id} ({i+1}/{total_pending})"
                    )
                    
                    task_start = time.time()

                    logger.info(f"🧠 [AI-Process] Synthesizing outline for [{asset_type}] : {asset_id}")
                    
                    outline = await self._ask_deepseek_for_outline(context, asset_type)

                    logger.info(f"📤 [Messenger] Archiving structured data for {asset_id}...")
                    await asyncio.to_thread(self.tools.call_messenger_back, asset_id, asset_type, outline)
                    
                    duration = time.time() - task_start
                    logger.info(f"✅ [Success] {asset_id} processed in {duration:.2f}s")

                except Exception as e:
                    logger.error(f"❌ [Error] Failed at {asset_id}: {str(e)}")
                finally:
                    self.state_manager.release_lock()
        except Exception as e:
            logger.error(f"🚨 [Global Crash] Critical error during ingestion: {str(e)}")
            self.state_manager.update_progress("Global", 0, f"Critical Error: {str(e)}")
        finally:
            # Absolute safety: ensure the system returns to IDLE
            if self.state_manager.get_status != SystemStatus.IDLE:
                self.state_manager.release_lock()
                logger.info("🔓 [Safety] Forced lock release after global sync completion/failure.")
        
        total_duration = time.time() - start_time
        logger.info(f"🏁 [Global Sync] Completed. Total time: {total_duration:.2f}s")

    async def _drive_raw_processing_suite(self):
        logger.info("🚀 [Toolbox] Launching raw processing suite (PDF/Video/Audio/Data)...")
        
        wrappers = [
            ("📄 PDF-Parser", self.tools.call_pdf_parser, {"mode": "all"}),
            ("📽️ Video-Slicer", self.tools.call_video_slicer, {"mode": "all"}),
            ("🎙️ Audio-Whisper", self.tools.call_whisper_node, {"mode": "all"}),
            ("📡 Data-Layer", self.tools.call_data_manager, {"target_type": "all", "force_reset": False})
        ]

        for name, func, params in wrappers:
            logger.info(f"⏳ [Running] {name} ...")
            self.state_manager.update_progress(name, 10, f"Starting {name}...") # 10% of the sub-task
            try:
                res = await asyncio.to_thread(func, params)
                if res.get("status") == "success":
                    logger.info(f"🟢 [Done] {name}")
                    milestones = {"📄 PDF-Parser": 20, "📽️ Video-Slicer": 40, "🎙️ Audio-Whisper": 60, "📡 Data-Layer": 80}
                    self.state_manager.update_progress("Pipeline", milestones.get(name, 0), f"Completed {name}")
                else:
                    logger.warning(f"🟡 [Warning] {name} reported issues: {res.get('message')}")
            except Exception as e:
                logger.error(f"🔴 [Crash] {name} failed: {str(e)}")

    async def _ask_deepseek_for_outline(self, context: str, asset_type: str):
        prompt = self.prompt_manager.render("structural_outline", raw_context=context, asset_type=asset_type)
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                self.api_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": "You are a professional academic assistant."},
                        {"role": "user", "content": prompt}
                    ],
                    "response_format": {"type": "json_object"}
                }
            )
            res_data = response.json()
            return json.loads(res_data['choices'][0]['message']['content'])