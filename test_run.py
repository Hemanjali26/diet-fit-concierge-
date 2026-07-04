import asyncio
import os
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.agent import app
from google.adk.runners import InMemoryRunner
from google.genai import types
from google.adk.events.request_input import RequestInput

async def main():
    print("--- Starting Agent End-to-End Test ---")
    print("Initializing runner...")
    runner = InMemoryRunner(app=app)
    
    session = await runner.session_service.create_session(
        app_name=app.name, user_id="test_user"
    )
    print(f"Session created: {session.id}")
    
    query = "Suggest a day's diet plan and workout schedule for a 25-year-old male, 80kg, 180cm, moderately active, who wants to build muscle and consume a high protein diet."
    print(f"User Query: {query}\n")
    
    print("Sending request to workflow graph...")
    async for event in runner.run_async(
        user_id="test_user",
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part.from_text(text=query)]),
    ):
        if event.content is not None:
            text = "".join(p.text for p in event.content.parts if p.text)
            print(f"\n[AGENT CONTENT EVENT]:\n{text}\n")
            
        if isinstance(event, RequestInput):
            print(f"--> Workflow Paused on Interrupt: {event.interrupt_id}")
            print("Resuming workflow with approval response: 'yes'...\n")
            
            async for resume_event in runner.run_async(
                user_id="test_user",
                session_id=session.id,
                resume_inputs={"user_approval": "yes"}
            ):
                if resume_event.content is not None:
                    res_text = "".join(p.text for p in resume_event.content.parts if p.text)
                    print(f"[AGENT RESUME CONTENT EVENT]:\n{res_text}\n")
                if resume_event.output is not None:
                    print(f"[WORKFLOW COMPLETE OUTPUT]: {resume_event.output}")

if __name__ == "__main__":
    asyncio.run(main())
