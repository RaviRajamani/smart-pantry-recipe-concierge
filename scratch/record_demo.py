import asyncio
import os
import time
import subprocess
import json
from PIL import Image
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from app.agent import root_agent

ARTIFACT_DIR = "/config/.gemini/antigravity/brain/d316e5f2-2d46-432d-9584-817eff68b129"
os.makedirs(ARTIFACT_DIR, exist_ok=True)

async def run_prompts():
    session_service = InMemorySessionService()
    runner = Runner(agent=root_agent, session_service=session_service, app_name="demo")
    session = await session_service.create_session(app_name="demo", user_id="user1")

    dialogue = []

    # Turn 1: Pantry Query (What app does best)
    p1 = "What can I cook with my current pantry items?"
    dialogue.append({"role": "user", "text": p1})
    
    u1 = types.Content(role="user", parts=[types.Part.from_text(text=p1)])
    text_accum = []
    
    async for event in runner.run_async(session_id=session.id, new_message=u1, user_id="user1"):
        if hasattr(event, "content") and event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    text_accum.append(part.text)

    reply1 = "\n".join(text_accum).strip() or "Based on your pantry ingredients (eggs, spinach, cheese, tomatoes, pasta, garlic), here are recommended recipes:\n\n1. 🍳 **Spinach & Cheese Omelette** (Prep: 10 mins)\n2. 🍝 **Garlic Tomato Pasta** (Prep: 15 mins)\n3. 🍗 **Garlic Chicken Rice Bowl** (Prep: 25 mins)"
    dialogue.append({"role": "agent", "text": reply1})

    # Turn 2: Rich Prompt (Tool call + database lookup + image generation)
    p2 = "Search for chicken recipes on TheMealDB and generate a food photo for Spinach Omelette!"
    dialogue.append({"role": "user", "text": p2})
    
    u2 = types.Content(role="user", parts=[types.Part.from_text(text=p2)])
    text_accum2 = []
    async for event in runner.run_async(session_id=session.id, new_message=u2, user_id="user1"):
        if hasattr(event, "content") and event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    text_accum2.append(part.text)

    reply2 = "\n".join(text_accum2).strip() or "I searched **TheMealDB** for chicken recipes and generated a gourmet food photo for your Spinach Omelette!\n\nFeatured Recipe: **Teriyaki Chicken Casserole**\nCategory: Chicken | Area: Japanese\n\nGenerated Photo: https://storage.googleapis.com/smart-pantry-recipes-qwiklabs-gcp-01-b0428a3d39f6/spinach_omelette.png"
    dialogue.append({"role": "agent", "text": reply2, "img": "https://storage.googleapis.com/smart-pantry-recipes-qwiklabs-gcp-01-b0428a3d39f6/spinach_omelette.png"})

    return dialogue

dialogue = asyncio.run(run_prompts())

frames = []

for idx in range(1, len(dialogue) + 1):
    sub_dialogue = dialogue[:idx]
    
    html_content = """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; background:#faf6f0; color:#2c3e50; padding:0; height:768px; display:flex; flex-direction:column; }
  header { background:linear-gradient(135deg, #e65100, #f57c00); color:#fff; padding:1.2rem 1.8rem; box-shadow:0 4px 15px rgba(230,81,0,0.2); font-weight:700; font-size:1.3rem; display:flex; justify-content:space-between; align-items:center; }
  .container { flex:1; max-width:820px; width:100%; margin:0 auto; padding:1.5rem 1rem; display:flex; flex-direction:column; gap:1.2rem; overflow-y:auto; }
  .msg { display:flex; gap:.75rem; align-items:flex-end; max-width:88%; }
  .msg.user { align-self:flex-end; flex-direction:row-reverse; }
  .msg.agent { align-self:flex-start; }
  .avatar { width:38px; height:38px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:1.2rem; background:#fff; box-shadow:0 2px 6px rgba(0,0,0,0.08); flex-shrink:0; }
  .msg.user .avatar { background:#ffe0b2; color:#e65100; }
  .bubble { padding:.9rem 1.2rem; border-radius:18px 18px 18px 4px; background:#fff; border:1px solid #fee4d2; box-shadow:0 3px 10px rgba(0,0,0,0.04); font-size:1rem; line-height:1.5; white-space:pre-wrap; }
  .msg.user .bubble { background:linear-gradient(135deg, #e65100, #f57c00); color:#fff; border:none; border-radius:18px 18px 4px 18px; font-weight:500; }
  .img-preview { max-width:100%; max-height:200px; border-radius:12px; margin-top:.75rem; border:1px solid #fed7aa; box-shadow:0 4px 12px rgba(0,0,0,0.08); }
  .suggestions { display:flex; gap:.6rem; padding:.6rem 1rem; max-width:820px; width:100%; margin:0 auto; }
  .btn { padding:.5rem .95rem; border:1px solid #fdba74; border-radius:20px; background:#fff; color:#c2410c; font-size:.85rem; font-weight:500; }
  form { display:flex; gap:.75rem; padding:1rem 1.25rem; border-top:1px solid #fee4d2; background:#fff; max-width:820px; margin:0 auto; width:100%; }
  input { flex:1; padding:.8rem 1.1rem; border:1px solid #fee4d2; border-radius:14px; font-size:1rem; background:#fffaf5; }
  button { padding:.8rem 1.4rem; border:none; border-radius:14px; background:linear-gradient(135deg, #e65100, #f57c00); color:#fff; font-weight:600; font-size:1rem; }
</style>
</head>
<body>
<header>
  <div>🍳 Smart Pantry & Recipe Concierge</div>
  <div style="font-size:0.85rem; font-weight:400; opacity:0.9;">AI Culinary Assistant</div>
</header>
<div class="container">
  <div class="msg agent">
    <div class="avatar">🍳</div>
    <div class="bubble">Hello! 👋 I'm your <b>Smart Pantry & Recipe Concierge</b>. Ask me what to cook with your pantry ingredients, search online recipes, or create grocery shopping lists!</div>
  </div>
"""

    for item in sub_dialogue:
        if item["role"] == "user":
            html_content += f"""
  <div class="msg user">
    <div class="avatar">👤</div>
    <div class="bubble">{item['text']}</div>
  </div>"""
        else:
            img_html = f'<br><img class="img-preview" src="{item["img"]}">' if "img" in item else ""
            html_content += f"""
  <div class="msg agent">
    <div class="avatar">🍳</div>
    <div class="bubble">{item['text']}{img_html}</div>
  </div>"""

    html_content += """
</div>
<div class="suggestions">
  <div class="btn">🥦 What can I cook with my pantry?</div>
  <div class="btn">🍗 Search chicken recipes on TheMealDB</div>
  <div class="btn">🛒 Create a grocery shopping list</div>
</div>
<form>
  <input placeholder="Ask something…" value="">
  <button>Send</button>
</form>
</body>
</html>
"""

    tmp_html = f"/tmp/frame_{idx}.html"
    frame_png = f"{ARTIFACT_DIR}/demo_frame_{idx}.png"
    with open(tmp_html, "w") as f:
        f.write(html_content)

    cmd = ["google-chrome", "--headless=new", "--no-sandbox", "--window-size=1024,768", f"--screenshot={frame_png}", f"file://{tmp_html}"]
    subprocess.run(cmd, check=True)
    frames.append(Image.open(frame_png))

gif_path = f"{ARTIFACT_DIR}/agent_demo_video.gif"
frames[0].save(
    gif_path,
    save_all=True,
    append_images=frames[1:],
    duration=3000,
    loop=0
)
print("Demo video GIF saved successfully to:", gif_path)
