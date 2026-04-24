from openai import AsyncOpenAI
from app.config import settings

client = AsyncOpenAI(
    api_key=settings.OPENAI_API_KEY,
    timeout=settings.OPENAI_TIMEOUT_SECONDS,
)

SYSTEM_PROMPT = """
You are Maiz, an indoor navigation AI assistant.
You help users navigate inside venues like malls, airports, supermarkets, and hospitals.
You give clear, landmark-based step-by-step directions.
Keep responses concise and actionable.
If the user asks about a product location, tell them which zone/aisle to go to.
Always reference visual landmarks (signs, pillars, escalators) in your directions.
"""


async def chat_completion(messages: list, stream: bool = True):
    response = await client.chat.completions.create(
        model=settings.OPENAI_CHAT_MODEL,
        messages=[{"role": "system", "content": SYSTEM_PROMPT}] + messages,
        stream=stream,
        max_tokens=500,
        temperature=0.4,
    )
    return response


async def transcribe_audio(audio_bytes: bytes, filename: str = "audio.webm") -> str:
    import io
    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = filename
    transcript = await client.audio.transcriptions.create(
        model=settings.OPENAI_TRANSCRIBE_MODEL,
        file=audio_file,
    )
    return transcript.text


async def analyze_image(image_url: str, context: str = "") -> dict:
    prompt = f"""
You are analyzing an indoor navigation photo.
Identify:
1. Venue type (mall, airport, supermarket, etc.)
2. Current zone or area name if visible
3. Any visible landmarks (store signs, aisle markers, escalators, pillars)
4. Any visible text (signs, aisle numbers)
5. Overall confidence (0.0 - 1.0) that you can identify the location

{f'Additional context: {context}' if context else ''}

Respond in JSON format only:
{{
  "detectedVenueType": "string or null",
  "detectedZone": "string or null",
  "detectedLandmarks": ["landmark1", "landmark2"],
  "detectedText": "string or null",
  "detectedLocation": "string or null",
  "overallConfidence": 0.0
}}
"""
    response = await client.chat.completions.create(
        model=settings.OPENAI_VISION_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": prompt},
                ],
            }
        ],
        max_tokens=500,
        response_format={"type": "json_object"},
    )
    import json
    return json.loads(response.choices[0].message.content)