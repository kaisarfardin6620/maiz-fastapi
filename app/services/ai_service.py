from openai import AsyncOpenAI
from app.config import settings

client = AsyncOpenAI(
    api_key=settings.OPENAI_API_KEY,
    timeout=settings.OPENAI_TIMEOUT_SECONDS,
)

SYSTEM_PROMPT = """
You are Maiz, a smart navigation AI assistant.
You handle BOTH outdoor and indoor navigation. 

CRITICAL INSTRUCTION: The user interface does NOT have a venue selector. You are 100% responsible for figuring out the user's location context.
If you need to know the user's current building/venue to give indoor directions, DO NOT ask them to type it. 
Instead, reply exactly and ONLY with this secret phrase at the very beginning of your response: [NEED_GPS]

This will trigger the app to request their device location.
Once the user provides their GPS coordinates (which will be automatically injected into your context), you can use the `route_to_location` or `search_venues` MCP tools to map their route.

Provide clear, landmark-based directions. Keep responses concise and actionable.
Do not output raw JSON coordinates to the user, just provide friendly directions.
"""

def build_system_prompt(user_context: dict | None = None) -> str:
    if not user_context:
        return SYSTEM_PROMPT

    identity_bits = []
    if user_context.get("fullName"):
        identity_bits.append(f"full name: {user_context['fullName']}")
    elif user_context.get("firstName") or user_context.get("lastName"):
        identity_bits.append(
            f"name: {(user_context.get('firstName') or '').strip()} {(user_context.get('lastName') or '').strip()}".strip()
        )
    if user_context.get("email"):
        identity_bits.append(f"email: {user_context['email']}")

    if not identity_bits:
        return SYSTEM_PROMPT

    return (
        f"{SYSTEM_PROMPT}\n\n"
        "Current authenticated user context:\n"
        f"- {', '.join(identity_bits)}\n"
    )

async def chat_completion(
    messages: list,
    stream: bool = True,
    user_context: dict | None = None,
    runtime_context: str | None = None,
):
    system_prompt = build_system_prompt(user_context)
    composed_messages = [{"role": "system", "content": system_prompt}]
    if runtime_context:
        composed_messages.append({"role": "system", "content": runtime_context})
    composed_messages.extend(messages)

    response = await client.chat.completions.create(
        model=settings.OPENAI_CHAT_MODEL,
        messages=composed_messages,
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
You are analyzing an indoor navigation photo. Identify:
1. Venue type (mall, airport, supermarket, etc.)
2. Current zone or area name if visible
3. Visible landmarks (signs, escalators)
4. Overall confidence (0.0 - 1.0)
{f'Context: {context}' if context else ''}

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