import os
import sys
from dotenv import load_dotenv

# Add src to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.local_provider import LocalProvider

def test_local_phi3():
    load_dotenv()
    model_path = os.getenv("LOCAL_MODEL_PATH", "./models/Phi-3-mini-4k-instruct-q4.gguf")
    
    print(f"--- Testing Local Provider with Phi-3 ---")
    print(f"Model Path: {model_path}")
    
    if not os.path.exists(model_path):
        print(f"❌ Error: Model file not found at {model_path}")
        print("Please download it from Hugging Face and place it in the models/ folder.")
        return

    try:
        provider = LocalProvider(model_path=model_path)
        
        prompt = "Explain what an AI Agent is in one sentence."
        print(f"\nUser: {prompt}")
        print("Assistant: ", end="", flush=True)
        
        for chunk in provider.stream(prompt):
            print(chunk, end="", flush=True)
        print("\n\n✅ Local Provider is working correctly!")
        
    except Exception as e:
        print(f"\n❌ Error during execution: {e}")

if __name__ == "__main__":
    test_local_phi3()
