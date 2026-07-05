# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
import os
import re
import sys
from typing import AsyncGenerator
from pydantic import BaseModel, Field

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App, ResumabilityConfig
from google.adk.models import Gemini
from google.adk.tools import AgentTool
from google.adk.workflow import Workflow, START
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.agents.context import Context
from google.genai import types

from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

from app.config import config

# --- MODELS ---
gemini_model = Gemini(
    model=config.model,
    retry_options=types.HttpRetryOptions(attempts=1),
)

# --- MCP SERVER CONFIGURATION ---
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
mcp_script = os.path.join(project_root, "app", "mcp_server.py")

mcp_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command=sys.executable,
            args=[mcp_script],
        )
    )
)

# --- SCHEMAS ---
class DietFitState(BaseModel):
    user_query: str = ""
    diet_plan: str = ""
    workout_plan: str = ""
    grocery_list: str = ""
    preparation_steps: str = ""
    feedback: str = ""
    is_approved: bool = False
    security_passed: bool = True
    audit_log: list[dict] = []
    run_workout_next: bool = False

async def init_agent_state(callback_context: CallbackContext) -> None:
    if "user_query" not in callback_context.state:
        callback_context.state["user_query"] = ""
    if "feedback" not in callback_context.state:
        callback_context.state["feedback"] = ""

# --- SUB-AGENTS ---
diet_agent = LlmAgent(
    name="diet_agent",
    model=gemini_model,
    instruction="""You are a professional Nutritionist and Dietitian.
Your job is to generate a comprehensive full-day diet plan (breakfast, lunch, dinner, snacks) based on the user's requirements.

Original Request: {user_query}
User Feedback (if any): {feedback}

You must also compile a consolidated grocery list for all ingredients needed, and provide step-by-step preparation/cooking instructions.
Make sure the diet is healthy, balanced, and matches the user's goals (e.g. weight loss, muscle gain, low carb, etc.).
You have access to MCP tools to calculate macros based on the calorie targets, and lookup nutrition details of typical foods. Use these tools whenever appropriate to ensure accuracy!""",
    tools=[mcp_toolset],
    description="Generates a customized full-day diet plan, grocery list, and meal preparation instructions.",
    before_agent_callback=init_agent_state,
)

workout_agent = LlmAgent(
    name="workout_agent",
    model=gemini_model,
    instruction="""You are a certified Personal Trainer and Fitness Coach.
Your job is to design a tailored workout schedule for the user based on their fitness goals, experience level, and preferences.

Original Request: {user_query}
User Feedback (if any): {feedback}

Include specific exercises, sets, reps, durations, and rest times.
You have access to an MCP tool to calculate the user's BMI and TDEE (maintenance calories) to ensure your workout recommendation is mathematically aligned with their weight goals. Use this tool!""",
    tools=[mcp_toolset],
    description="Designs a personalized workout schedule based on user fitness goals and constraints.",
    before_agent_callback=init_agent_state,
)

# --- WORKFLOW FUNCTIONS ---

import json
import logging

# Initialize standard logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("diet_fit_security")

def security_checkpoint(ctx: Context, node_input: types.Content) -> Event:
    text = ""
    if node_input and node_input.parts:
        text = "".join(p.text for p in node_input.parts if p.text)
    
    # 1. Prompt Injection Detection
    injection_keywords = [
        "ignore previous instructions", 
        "system prompt", 
        "override instructions",
        "you are now a", 
        "dan mode", 
        "do anything now", 
        "jailbreak", 
        "forget your guidelines"
    ]
    is_injection = any(kw in text.lower() for kw in injection_keywords)
    
    if is_injection:
        audit_entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "event": "security_checkpoint",
            "severity": "CRITICAL",
            "reason": "Potential prompt injection detected",
            "action": "BLOCK"
        }
        ctx.state.setdefault("audit_log", []).append(audit_entry)
        logger.warning(json.dumps(audit_entry))
        return Event(output="Security Checkpoint Blocked Request: Prompt Injection Detected", route="fail", state={"security_passed": False})
    
    # 2. Domain-Specific Security Rules
    # Rule A: COPPA / Underage safety check (block under 13)
    underage_patterns = [
        r"\b(?:under|being|i am|i'm)?\s*(?:12|11|10|9|8|7|6|5)\s*(?:years?\s*old|y/o|yo)\b",
        r"\bchild of\s*(?:12|11|10|9|8|7|6|5)\b"
    ]
    is_underage = any(re.search(pat, text.lower()) for pat in underage_patterns)
    if is_underage:
        audit_entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "event": "security_checkpoint",
            "severity": "CRITICAL",
            "reason": "COPPA violation: user is under 13 years of age",
            "action": "BLOCK"
        }
        ctx.state.setdefault("audit_log", []).append(audit_entry)
        logger.warning(json.dumps(audit_entry))
        return Event(output="Security Checkpoint Blocked Request: User is under 13", route="fail", state={"security_passed": False})

    # Rule B: Medical diagnosis or prescription drug query restriction
    medical_patterns = [
        r"\bozempic\b", r"\binsulin\b", r"\bprescribe\b", r"\bprescription\b",
        r"\bdiagnose\b", r"\bcure cancer\b", r"\bheart attack\b", r"\bmedication\b"
    ]
    is_medical_request = any(re.search(pat, text.lower()) for pat in medical_patterns)
    if is_medical_request:
        audit_entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "event": "security_checkpoint",
            "severity": "WARNING",
            "reason": "Medical prescription or diagnostic inquiry detected",
            "action": "BLOCK"
        }
        ctx.state.setdefault("audit_log", []).append(audit_entry)
        logger.warning(json.dumps(audit_entry))
        return Event(output="Security Checkpoint Blocked Request: Medical diagnosis/prescription request is not allowed", route="fail", state={"security_passed": False})

    # 3. PII Scrubbing
    cleaned_text = re.sub(r'[\w\.-]+@[\w\.-]+\.\w+', '[REDACTED_EMAIL]', text)
    cleaned_text = re.sub(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', '[REDACTED_PHONE]', cleaned_text)
    cleaned_text = re.sub(r'\b(?:\d[ -]*?){13,16}\b', '[REDACTED_CARD]', cleaned_text)
    cleaned_text = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[REDACTED_SSN]', cleaned_text)
    cleaned_text = re.sub(r'\b[A-Z]{3}\d{8,10}\b', '[REDACTED_INSURANCE]', cleaned_text)
    
    ctx.state["user_query"] = cleaned_text
    
    audit_entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "event": "security_checkpoint",
        "severity": "INFO",
        "reason": "Request passed security checks successfully",
        "action": "ALLOW"
    }
    ctx.state.setdefault("audit_log", []).append(audit_entry)
    logger.info(json.dumps(audit_entry))
    
    return Event(output=cleaned_text, route="pass", state={"security_passed": True})


def security_event(ctx: Context, node_input: str) -> Event:
    err_msg = "Your request was blocked due to a security policy violation (potential prompt injection or unsafe content)."
    yield Event(content=types.Content(role='model', parts=[types.Part.from_text(text=err_msg)]))
    yield Event(output=err_msg)


async def human_approval(ctx: Context, node_input: str) -> AsyncGenerator[Event, None]:
    plan_text = node_input
        
    if not ctx.resume_inputs or "user_approval" not in ctx.resume_inputs:
        plan_summary = (
            f"### Proposed Health & Fitness Plan\n\n"
            f"{plan_text}\n\n"
            f"Please review the plan. Do you approve? Enter 'yes' or specify feedback for changes."
        )
        yield Event(content=types.Content(role='model', parts=[types.Part.from_text(text=plan_summary)]))
        yield RequestInput(interrupt_id="user_approval", message="Do you approve this plan? Enter 'yes' or describe changes you'd like.")
        return

    user_resp = ctx.resume_inputs["user_approval"].strip()
    if user_resp.lower() == "yes":
        yield Event(output=plan_text, route="approve", state={"is_approved": True})
    else:
        yield Event(output=user_resp, route="revise", state={"feedback": user_resp})


def final_output(ctx: Context, node_input: str) -> Event:
    # Check if the flow is from security failure or approved plan
    if not ctx.state.get("security_passed", True):
        # Already output in security_event, just return it
        return Event(output="Request Blocked")
        
    final_text = (
        f"🎉 **Your Customized Diet & Fitness Plan is Ready and Approved!**\n\n"
        f"{node_input}"
    )
    yield Event(content=types.Content(role='model', parts=[types.Part.from_text(text=final_text)]))
    yield Event(output=node_input)


# --- WORKFLOW GRAPH CONFIGURATION ---

def request_router(ctx: Context, node_input: str) -> Event:
    ctx.state["user_query"] = node_input
    text = node_input.lower()
    
    # Determine user intent
    wants_diet = any(w in text for w in ["diet", "food", "eat", "meal", "calorie", "protein", "nutrition", "grocery", "prep"]) or not ("workout" in text or "exercise" in text or "gym" in text or "train" in text)
    wants_workout = any(w in text for w in ["workout", "exercise", "gym", "train", "schedule", "fitness", "active", "tdee", "bmi"])
    
    if wants_diet and wants_workout:
        return Event(output=node_input, route="run_diet", state={"run_workout_next": True, "diet_plan": "", "workout_plan": ""})
    elif wants_workout:
        return Event(output=node_input, route="workout", state={"run_workout_next": False, "diet_plan": "", "workout_plan": ""})
    else:
        return Event(output=node_input, route="run_diet", state={"run_workout_next": False, "diet_plan": "", "workout_plan": ""})


def after_diet_router(ctx: Context, node_input: str) -> Event:
    ctx.state["diet_plan"] = node_input
    if ctx.state.get("run_workout_next", False):
        return Event(output=ctx.state["user_query"], route="run_workout")
    else:
        return Event(output=node_input, route="approve_flow")


def after_workout_router(ctx: Context, node_input: str) -> Event:
    ctx.state["workout_plan"] = node_input
    diet = ctx.state.get("diet_plan", "")
    workout = ctx.state.get("workout_plan", "")
    
    plan_text = ""
    if diet:
        plan_text += f"## 🍽️ Diet and Nutrition Plan\n\n{diet}\n\n"
    if workout:
        plan_text += f"## 🏋️ Workout and Fitness Schedule\n\n{workout}"
        
    return Event(output=plan_text.strip())


root_agent = Workflow(
    name="diet_fit_concierge_workflow",
    edges=[
        (START, security_checkpoint),
        (security_checkpoint, {"pass": request_router, "fail": security_event}),
        
        (request_router, {"run_diet": diet_agent, "workout": workout_agent}),
        
        (diet_agent, after_diet_router),
        (after_diet_router, {"run_workout": workout_agent, "approve_flow": human_approval}),
        
        (workout_agent, after_workout_router),
        (after_workout_router, human_approval),
        
        (human_approval, {"approve": final_output, "revise": request_router}),
        (security_event, final_output),
    ],
    state_schema=DietFitState,
)

app = App(
    name="app",
    root_agent=root_agent,
    resumability_config=ResumabilityConfig(is_resumable=True),
)
