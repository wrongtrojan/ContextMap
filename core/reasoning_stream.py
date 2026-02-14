import logging
import asyncio
import os
import json
import httpx
import yaml
from typing import List, Dict, Any, TypedDict
from pathlib import Path
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.redis import AsyncRedisSaver
from langchain_core.callbacks.manager import adispatch_custom_event
from dotenv import load_dotenv

# Internal core components
from core.tools_manager import ToolsManager
from core.system_state import SystemStateManager
from core.prompt_manager import PromptManager

# Standard logging configuration
logger = logging.getLogger("ReasoningStream")
load_dotenv()

class AgentState(TypedDict):
    """
    Main state object for LangGraph, capturing the context across nodes.
    Aligned with PROPOSAL.md for academic reasoning and pruning.
    """
    query: str
    retrieved_docs: List[Dict]
    verification_results: str  # Store sandbox strings or results
    vlm_feedback: str
    reasoning_chain: List[str]
    final_answer: str
    citations: List[Dict[str, Any]]
    graph_data: Dict[str, Any]
    status: str
    task_manifest: Dict[str, Any] # New: Intent-driven task list
    has_video: bool               # Routing flag
    eval_report: Dict[str, Any]   
    retry_count: int              

class ReasoningStream:
    def __init__(self, tools_manager: ToolsManager):
        """
        Initialize the reasoning engine with tool gateway and VRAM guard.
        """
        self.tools = tools_manager
        self.state_manager = SystemStateManager()
        self.prompt_manager = PromptManager()
        self.project_root = Path(__file__).resolve().parent.parent
        
        # API Configurations from .env
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        self.base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        
        # Redis setup for state persistence and checkpointing
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        logger.info(f"Redis Persistence active at {self.redis_url}")
        
        # Load Global Strategies
        strategy_path = self.project_root / "configs" / "strategies.yaml"
        with open(strategy_path, 'r', encoding='utf-8') as f:
            self.strategies = yaml.safe_load(f)

    async def _check_resource_lock(self) -> bool:
        """
        Interrogates the SystemStateManager to ensure VRAM is available.
        Prevents collision with Track A (Ingestion).
        """
        if not self.state_manager.is_query_allowed():
            logger.error("VRAM Guard: Query denied. Ingestion task in progress.")
            return False
        return True
    
    async def _deepseek_call(self, prompt: str, json_mode: bool = False, stream:bool=False) -> Any:
        """Standard DeepSeek API caller."""
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "stream":stream
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            client = httpx.AsyncClient(timeout=60.0)
            if stream:
                return client.stream("POST", f"{self.base_url}/chat/completions", headers=headers, json=payload, timeout=60.0)
            
            async with client:
                response = await client.post(
                    f"{self.base_url}/chat/completions", 
                    headers=headers, 
                    json=payload, 
                    timeout=60.0
                )
                raw_content = response.json()['choices'][0]['message']['content']
                return json.loads(raw_content) if json_mode else raw_content
        except Exception as e:
            logger.error(f"DeepSeek API Error: {str(e)}")
            return {"error": str(e)}
        
    def _clean_json_string(self, raw_str: str) -> str:
        """Removes Markdown code blocks and extra whitespace for robust JSON parsing."""
        if not raw_str: return "{}"
        cleaned = raw_str.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        return cleaned

    # --- Node Implementations ---

    async def research_node(self, state: AgentState) -> Dict:
        """Retrieval Node: Fetches structured evidence."""
        query = state["query"]
        logger.info(f"🔍 [Node: Research] Fetching evidence for: {query[:30]}...")

        retry_idx = state.get("retry_count", 0)
        logger.info(f"🔍 [Node: Research] Attempt {retry_idx + 1} | Query: {query[:30]}...")
        
        refine_prompt = self.prompt_manager.render(
            "query_refiner", 
            query=query, 
            is_retry=(retry_idx > 0) 
        )
        refine_json = await self._deepseek_call(refine_prompt, json_mode=True)
        
        if isinstance(refine_json, str):
            refine_json = json.loads(self._clean_json_string(refine_json)) 
        
        search_params = {
            "query": " ".join(refine_json.get("search_params", {}).get("keywords", [query])),
            "top_k": refine_json.get("search_params", {}).get("top_k", 5),
            "preferences": refine_json.get("preferences") 
        }
        
        raw_res = await asyncio.to_thread(self.tools.call_searcher, search_params)
        
        if isinstance(raw_res, list):
            structured_citations = []
            has_video = any(d.get("metadata", {}).get("modality") == "video" for d in raw_res)
            for doc in raw_res:
                meta = doc.get("metadata", {})
                modality = meta.get("modality")
                
                cite_item = {"type": modality, "asset_name": meta.get("asset_name")}
                if modality == "video":
                    has_video = True
                    ts = float(meta.get("timestamp", 0))
                    cite_item.update({"seconds": ts, "label": f"{int(ts)//60:02d}:{int(ts)%60:02d}"})
                elif modality == "pdf":
                    page = meta.get("page_label", "0")
                    cite_item.update({"page": int(page), "bbox": meta.get("bbox", [])})
            
                structured_citations.append(cite_item)
                
            # Intent Analysis: Decide if we need Vision or Sandbox
            intent_prompt = self.prompt_manager.render("intent_check", query=query, docs=raw_res, any_video=has_video)
            manifest = await self._deepseek_call(intent_prompt, json_mode=True)
            
            return {
                "retrieved_docs": raw_res,
                "citations": list(structured_citations),
                "has_video": has_video,
                "task_manifest": manifest,
                "reasoning_chain": state["reasoning_chain"] + [f"Retrieved {len(raw_res)} docs. Intent: {manifest.get('reasoning_focus')}"],
                "status": "researched"
            }
        return {"status": "error", "reasoning_chain": state["reasoning_chain"] + ["Search failed."]}

    async def evaluate_node(self, state: AgentState) -> Dict:
        """Auditor Node: Evaluates relevance and decides tool triggers."""
        logger.info("⚖️ [Node: Evaluate] Auditing evidence relevance...")
        
        current_retry = state.get("retry_count", 0)
        
        eval_prompt = self.prompt_manager.render(
            "evidence_evaluator", 
            query=state["query"], 
            docs=state["retrieved_docs"]
        )
        eval_report = await self._deepseek_call(eval_prompt, json_mode=True)
        
        if isinstance(eval_report, str):
            try:
                eval_report = json.loads(self._clean_json_string(eval_report))
            except:
                eval_report = {"action": "proceed"}
        
        if current_retry >= 2 and eval_report.get("action") == "refetch":
            logger.warning(f"⚠️ Max retries ({current_retry + 1}) reached. Forcing 'proceed' with current evidence.")
            eval_report["action"] = "proceed"
        
        # Override manifest based on evaluation
        updated_manifest = state["task_manifest"].copy()
        if eval_report.get("trigger_tools"):
            tools_to_check = eval_report["trigger_tools"]
            
            if tools_to_check.get("call_reasoning_eye") is True:
                updated_manifest["need_vision"] = True
            
            if tools_to_check.get("call_sandbox") is True:
                updated_manifest["need_sandbox"] = True
        
        return {
            "eval_report": eval_report,
            "task_manifest": updated_manifest,
            "retry_count": current_retry + 1 if eval_report.get("action") == "refetch" else current_retry,
            "reasoning_chain": state["reasoning_chain"] + [f"Audit Result: {eval_report.get('action')}"]
        }
    
    async def vision_node(self, state: AgentState) -> Dict:
        """Visual Expert Node: Analyzes frames based on intent strategy."""
        if not state.get("has_video") or not state["task_manifest"].get("need_vision"):
            return {"status": "vision_skipped"}

        logger.info("🎨 [Node: Vision] Analyzing video frames for visual evidence...")
        video_docs = [d for d in state["retrieved_docs"] if d.get("metadata", {}).get("modality") == "video"]
        
        top_video = video_docs[0]
        asset_name = top_video["metadata"].get("asset_name")
        ts = (top_video["metadata"].get("timestamp", 0))
        
        # Path aligned with your provided structure
        frame_path = self.project_root / "storage" / "processed" / "video" / asset_name / "frames" / f"time_{ts}.jpg"
        
        strategy_key = state["task_manifest"].get("vision_strategy", "scene_description")
        vlm_instruction = self.strategies.get("expert_strategies", {}).get("vision_eye", {}).get(
            strategy_key, "Please describe the visual content of this frame."
        )

        if frame_path.exists():
            vlm_params = {
                "image": str(frame_path),
                "prompt": f"{vlm_instruction} Context: {state['query']}"
            }
            vlm_res = await asyncio.to_thread(self.tools.call_reasoning_eye, vlm_params)
            
            return {
                "vlm_feedback": vlm_res.get("response", "Vision parse failed."),
                "reasoning_chain": state["reasoning_chain"] + [f"Node: vision_eye | Analyzed frame at {ts}s using {strategy_key} strategy."]
            }
        return {"vlm_feedback": "Frame not found."}

    async def logic_node(self, state: AgentState) -> Dict:
        """Verification Node: Prepares SymPy code via DeepSeek then runs Sandbox."""
        if not state["task_manifest"].get("need_sandbox"):
            return {"verification_results": "No verification required."}

        logger.info("🧠 [Node: Logic] Invoking DeepSeek for formula extraction...")
        combined_content = " ".join([d["content"] for d in state["retrieved_docs"]])
        
        prep_prompt = self.prompt_manager.render("sandbox_prep", context=combined_content)
        prep_res = await self._deepseek_call(prep_prompt, json_mode=True)
        
        if prep_res.get("expression") != "empty":
            logger.info(f"🔢 [Node: Logic] Invoking Sandbox for {prep_res.get('target_variable')}...")
            res = await asyncio.to_thread(self.tools.call_sandbox, prep_res)
            verification = f"Verified: {res.get('result')}"
        else:
            verification = "No complex formulas extracted."
            
        return {
            "verification_results": verification,
            "reasoning_chain": state["reasoning_chain"] + [f"Logic check: {verification}"]
        }

    async def synthesize_node(self, state: AgentState) -> Dict:
        """Synthesis Node: Finalizes the answer with CoT pruning."""
        logger.info("✍️ [Node: Synthesis] Finalizing academic response...")
        
        synth_prompt = self.prompt_manager.render(
            "synthesizer",
            query=state["query"],
            docs=state["retrieved_docs"],
            vlm_feedback=state.get("vlm_feedback"),
            math_res=state.get("verification_results"),
            eval_report=state.get("eval_report") 
        )
        
        full_answer = ""
        response_ctx = await self._deepseek_call(synth_prompt, stream=True)
        
        async with response_ctx as response:
            async for line in response.aiter_lines():
                if not line.startswith("data: "): continue
                if "[DONE]" in line: break
                
                try:
                    chunk = json.loads(line[6:])
                    token = chunk['choices'][0]['delta'].get('content', "")
                    if token:
                        full_answer += token
                        await adispatch_custom_event("academic_token", {"content": token})
                except:
                    continue
        
        mock_graph = {"nodes": [], "links": []}
        
        return {
            "final_answer": full_answer,
            "graph_data": mock_graph,
            "status": "completed",
            "reasoning_chain": state["reasoning_chain"] + ["Synthesis complete. Pruned CoT."]
        }

    def _build_workflow(self,saver):
        """Assembles the LangGraph state machine with Reflective Retrieval Loop."""
        workflow = StateGraph(AgentState)

        workflow.add_node("research", self.research_node)
        workflow.add_node("evaluate", self.evaluate_node)
        workflow.add_node("vision_eye", self.vision_node)
        workflow.add_node("verify", self.logic_node)
        workflow.add_node("synthesize", self.synthesize_node)

        workflow.set_entry_point("research")
        
        def route_after_research(state: AgentState):
            if state.get("status") == "error": return END
            return "evaluate"

        def route_after_evaluate(state: AgentState):
            report = state.get("eval_report", {})
            action = report.get("action")
            
            if action == "refetch" and state.get("retry_count", 0) < 2:
                logger.warning("🔄 Evidence insufficient, triggering refetch...")
                return "research"
            
            if state["task_manifest"].get("need_vision"):
                return "vision_eye"
            return "verify"
        
        workflow.add_conditional_edges("research", route_after_research)
        workflow.add_conditional_edges("evaluate", route_after_evaluate)
        workflow.add_edge("vision_eye", "verify")
        workflow.add_edge("verify", "synthesize")
        workflow.add_edge("synthesize", END)
        
        return workflow.compile(checkpointer=saver)
    
    async def stream_query(self, query: str, thread_id: str):
        """
        [Phase 2 Surgery] 
        Replaces execute_query. Uses astream_events (v2) to yield real-time 
        signals (Node starts, LLM tokens, Final results).
        """
        # 1. Resource Guard
        if not self.state_manager.acquire_query_lock():
            current_status_val = self.state_manager.get_status.value
            logger.warning(f"🚨 VRAM Conflict: Blocking query. System status: {current_status_val}")
            yield json.dumps({
                "event": "error", 
                "content": f"VRAM Locked: System is currently {current_status_val}. Please wait."
            }, ensure_ascii=False)
            return

        # 2. Transition State
        # Directly setting protected attribute for simplicity in this logic flow
        
        try:
            config = {"configurable": {"thread_id": thread_id}}
            async with AsyncRedisSaver.from_conn_string(self.redis_url) as saver:
                app = self._build_workflow(saver)
                
                initial_state = {
                    "query": query, "retrieved_docs": [], "verification_results": "",
                    "vlm_feedback": "", "reasoning_chain": [f"Init: {query}"],
                    "final_answer": "", "citations": [], "status": "started",
                    "task_manifest": {}, "has_video": False, "graph_data": {},
                    "eval_report": {}, "retry_count": 0
                }

                # Start LangGraph Event Stream (v2)
                async for event in app.astream_events(initial_state, config, version="v2"):
                    kind = event["event"]
                    name = event["name"]

                    # A. Capture Node Transitions
                    # Filter for our specific logic nodes defined in _build_workflow
                    if kind == "on_chain_start" and name in ["research", "evaluate", "vision_eye", "verify", "synthesize"]:
                        yield json.dumps({
                            "event": "node_start",
                            "node": name,
                            "message": f"Agent entering: {name}"
                        },ensure_ascii=False)

                    # B. Capture LLM Tokens (from the synthesize node or others)
                    elif kind == "on_chat_model_stream":
                        # data["chunk"] is the MessageChunk object
                        content = event["data"]["chunk"].content
                        if content:
                            yield json.dumps({
                                "event": "token",
                                "content": content
                            },ensure_ascii=False)

                    # C. Final result extraction when the whole graph ends
                    elif kind == "on_chain_end" and name == "LangGraph":
                        final_output = event["data"]["output"]
                        yield json.dumps({
                            "event": "final_result",
                            "citations": final_output.get("citations", []),
                            "status": "completed"
                        },ensure_ascii=False)
                    elif kind == "on_custom_event" and event["name"] == "academic_token":
                        yield json.dumps({
                            "event": "token",
                            "content": event["data"]["content"]   
                        },ensure_ascii=False)
        except GeneratorExit:
            logger.warning(f"🔌 Client dropped connection for thread {thread_id}")

        except Exception as e:
            logger.error(f"🔴 Streaming reasoning failed: {str(e)}")
            yield json.dumps({"event": "error", "content": str(e)})
        finally:
            # Absolute Safety: return to IDLE regardless of success or crash
            self.state_manager.release_lock()
            logger.info(f"🔓 [Stream] Lock released for thread {thread_id}")