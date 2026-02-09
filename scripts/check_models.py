"""
Check available Gemini models
"""
import os
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

print("Available models:")
print("=" * 50)

for model in genai.list_models():
    print(f"- {model.name}")
    if "imagen" in model.name.lower() or "image" in model.name.lower():
        print(f"  ^ IMAGE GENERATION MODEL")
    if "gemini" in model.name.lower():
        print(f"  Supported methods: {model.supported_generation_methods}")
