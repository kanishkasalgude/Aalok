"""
Step 2 of the agent pipeline: the Gemini function-calling loop, generalized
from agent.py's food-only single-tool loop (`retrieve_dishes` +
`finalize_recommendation`) to drive the full tool layer in tools.py. The
model may call any tool in tools.ALL_TOOL_DECLARATIONS any number of times
(bounded by max_turns), then must call `finalize_recommendation` exactly
once as its last action - a forced structured-output step, same pattern as
the original.

`finalize_recommendation` is NOT part of tools.ALL_TOOL_DECLARATIONS - it's
loop control, not a commerce operation, and orchestrator.py is the only
place that ever adds it to the tool list handed to the model.

Bounded by a hard overall timeout (integrations/llm/gemini.py) so an
unreachable API degrades to commerce_agent.py's deterministic fallback
instead of hanging the request.
"""
from __future__ import annotations

import json
from typing import Optional

from ...core.config import get_settings
from ...domain.commerce.intent import Intent
from ...integrations.llm.gemini import call_with_timeout, gemini_unreachable, llm_api_key
from . import tools

FINALIZE_TOOL_DECLARATION = {
    "name": "finalize_recommendation",
    "description": ("Submit the final structured recommendation once you have identified the best primary "
                     "product (and optionally one grounded complement) from your search_catalog/get_product "
                     "results. Call this exactly once, as your last action."),
    "parameters": {
        "type": "object",
        "properties": {
            "merchant_id": {"type": "string", "description": "Merchant id the primary product belongs to."},
            "primary_product_id": {"type": "string"},
            "primary_reasoning": {"type": "string"},
            "upsell_product_id": {"type": "string", "description": "Optional - a product id from find_complements' results, or empty string."},
            "upsell_reasoning": {"type": "string"},
        },
        "required": ["merchant_id", "primary_product_id", "primary_reasoning"],
    },
}

SYSTEM_INSTRUCTION = (
    "You are Aalok's AI shopping orchestrator. You help users find and buy products across food, "
    "grocery, fashion, beauty, electronics, jewellery, entertainment and services merchants. You MUST call "
    "search_catalog at least once before recommending anything - never invent a product. You MUST call "
    "finalize_recommendation exactly once as your final action, choosing a product id only from what "
    "search_catalog/get_product actually returned. Only propose an upsell if find_complements returned it - "
    "never invent a pairing; leave upsell_product_id empty otherwise. You have NO ability to create an order, "
    "charge a payment, or override any policy decision - those happen only after the user confirms, through "
    "Aalok's own deterministic backend."
)


def _genai_model():
    import google.generativeai as genai
    api_key = llm_api_key()
    if not api_key:
        return None
    genai.configure(api_key=api_key)
    tool_list = [{"function_declarations": tools.ALL_TOOL_DECLARATIONS + [FINALIZE_TOOL_DECLARATION]}]
    return genai.GenerativeModel("gemini-2.0-flash", tools=tool_list, system_instruction=SYSTEM_INSTRUCTION)


def run_tool_loop(user_text: str, intent: Intent, session_id: str, max_turns: int = 4) -> Optional[dict]:
    settings = get_settings()
    if settings.llm_provider != "gemini" or gemini_unreachable() or _genai_model() is None:
        return None
    return call_with_timeout(_run_tool_loop_call, user_text, intent, session_id, max_turns, timeout=20.0)


def _run_tool_loop_call(user_text: str, intent: Intent, session_id: str, max_turns: int) -> Optional[dict]:
    import google.generativeai as genai
    chat = _genai_model().start_chat()
    prompt = (f"User said: \"{user_text}\"\nParsed intent so far: {json.dumps(intent.to_dict())}\n"
              f"session_id for any cart tools: {session_id}\nFind and recommend the best match.")

    trace = []
    result = None
    try:
        response = chat.send_message(prompt)
        for _ in range(max_turns):
            fn_call = None
            for part in response.candidates[0].content.parts:
                if getattr(part, "function_call", None) and part.function_call.name:
                    fn_call = part.function_call
                    break
            if fn_call is None:
                break

            args = {k: v for k, v in fn_call.args.items()}

            if fn_call.name == "finalize_recommendation":
                trace.append({"tool": "finalize_recommendation", "args": args})
                result = {"args": args, "trace": trace}
                break

            func = tools.NAME_TO_FUNC.get(fn_call.name)
            tool_result = func(**args) if func else {"error": f"Unknown tool '{fn_call.name}'."}
            trace.append({"tool": fn_call.name, "args": args,
                           "result_count": len(tool_result.get("results", [])) if "results" in tool_result else None})
            response = chat.send_message(
                genai.protos.Content(parts=[genai.protos.Part(
                    function_response=genai.protos.FunctionResponse(name=fn_call.name, response=tool_result)
                )])
            )
    except Exception as e:
        trace.append({"tool": "error", "args": {"message": str(e)}})
        result = None

    if result is None:
        return {"args": None, "trace": trace}
    return result
