from openai import OpenAI
import os
OpenAIClient = OpenAI(api_key=os.getenv("OPEN_AI_KEY"))