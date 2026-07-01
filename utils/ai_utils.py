"""AI utilities for interpreting statistics, generating communications and narratives."""

import json
import os

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


def get_openai_client():
    """Get OpenAI client if API key is configured."""
    api_key = os.environ.get('OPENAI_API_KEY', '')
    if not api_key:
        return None
    try:
        return OpenAI(api_key=api_key)
    except Exception:
        return None


def interpret_statistics(data_text, title=""):
    """Send statistics data to AI and get back a summary + chart suggestions."""
    client = get_openai_client()
    if not client:
        return {
            'summary': 'AI interpretation unavailable — configure OPENAI_API_KEY.',
            'chart_type': 'bar',
            'insights': ['No AI insights available without API key.']
        }

    prompt = (
        'You are a change management analytics interpreter.\n\n'
        f'Given the following dataset titled "{title}", analyse it and return a JSON object with:\n'
        '- "summary": A 2-3 sentence executive summary of what the data tells us\n'
        '- "chart_type": The most appropriate chart type (bar, line, pie, doughnut, radar, polarArea)\n'
        '- "chart_labels": Array of labels for the x-axis / segments\n'
        '- "chart_values": Array of numeric values\n'
        '- "chart_label": The label for the dataset (e.g. "Completion Rate")\n'
        '- "insights": Array of 3-5 key insights a change manager should know\n'
        '- "recommendations": Array of 2-3 recommended actions based on the data\n'
        '- "kpi_cards": Array of objects with {"label": str, "value": str, '
        '"change": str (positive/negative/neutral), "icon": str}\n\n'
        f'DATA:\n{data_text[:8000]}\n'
    )
    try:
        response = client.chat.completions.create(
            model=os.environ.get('OPENAI_MODEL', 'gpt-4o-mini'),
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=2000,
        )
        text = response.choices[0].message.content
        result = json.loads(text)
        return result
    except Exception as e:
        return {
            'summary': 'AI interpretation error: ' + str(e),
            'chart_type': 'bar',
            'insights': ['Unable to process data at this time.']
        }


def generate_communication(audience_info, purpose, tone="professional", key_messages=None, brand=None):
    """Generate communication content tailored to an audience segment."""
    client = get_openai_client()
    if not client:
        return _fallback_communication(audience_info, purpose)

    msgs_text = ""
    if key_messages:
        if isinstance(key_messages, list):
            msgs_text = "KEY MESSAGES TO INCLUDE:\n" + "\n".join(f"- {m}" for m in key_messages)
        else:
            msgs_text = "KEY MESSAGES TO INCLUDE:\n" + key_messages

    brand_text = ""
    if brand:
        bn = brand.get('brand_name', 'CM Hub')
        pc = brand.get('primary_colour', '#1a1f36')
        ac = brand.get('accent_colour', '#e8a838')
        brand_text = f"Brand: {bn}\nPrimary colour: {pc}\nAccent colour: {ac}"

    audience_name = audience_info.get('name', 'Stakeholders')
    audience_desc = audience_info.get('description', '')
    audience_attrs = audience_info.get('attributes', '')
    audience_prefs = audience_info.get('communication_prefs', '')

    prompt = (
        'You are a change management communication specialist.\n\n'
        f'Generate a {tone} communication for the following audience and purpose.\n'
        'Return a JSON object with:\n'
        '- "subject": Email subject line\n'
        '- "greeting": Opening salutation\n'
        '- "body": Main body text (2-4 paragraphs, warm but professional)\n'
        '- "call_to_action": Clear next step for the reader\n'
        '- "closing": Sign-off text\n'
        '- "tone_notes": Short note on the tone used\n\n'
        f'AUDIENCE: {audience_name}\n'
        f'AUDIENCE DESCRIPTION: {audience_desc}\n'
        f'AUDIENCE ATTRIBUTES: {audience_attrs}\n'
        f'COMMUNICATION PREFS: {audience_prefs}\n\n'
        f'PURPOSE: {purpose}\n\n'
        f'{brand_text}\n'
        f'{msgs_text}\n\n'
        'Make the communication specific, actionable, and relevant to this audience. Use natural language.\n'
    )
    try:
        response = client.chat.completions.create(
            model=os.environ.get('OPENAI_MODEL', 'gpt-4o-mini'),
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.7,
            max_tokens=2000,
        )
        text = response.choices[0].message.content
        return json.loads(text)
    except Exception as e:
        return _fallback_communication(audience_info, purpose)


def _fallback_communication(audience_info, purpose):
    """Generate a basic communication without AI."""
    name = audience_info.get('name', 'Stakeholder')
    short_purpose = purpose[:60] if purpose else 'our current initiative'
    return {
        "subject": f"Update: {short_purpose}",
        "greeting": f"Dear {name},",
        "body": (
            f"We are writing to provide you with an update regarding {purpose}. "
            f"Your role as {name.lower()} is important to the success of this initiative. "
            f"We value your continued partnership and support.\n\n"
            f"Please review the information below and reach out to your change management "
            f"representative if you have any questions or require further clarification."
        ),
        "call_to_action": "Please review and share any feedback with your change management representative.",
        "closing": "Thank you for your continued support.\n\nChange Management Team",
        "tone_notes": "Professional, warm"
    }


def generate_narrative(narrative_type, context, audience_info=None, brand=None):
    """Generate a change narrative, vision statement, or talking points."""
    client = get_openai_client()
    if not client:
        return _fallback_narrative(narrative_type, context)

    audience_context = ""
    if audience_info:
        aname = audience_info.get('name', 'General')
        adesc = audience_info.get('description', '')
        audience_context = f"TARGET AUDIENCE: {aname}\nAUDIENCE DESCRIPTION: {adesc}\n"

    prompt = (
        'You are a strategic change communication advisor.\n\n'
        f'Create a {narrative_type.replace("_", " ")} based on the following context.\n'
        'Return a JSON object with:\n'
        '- "title": A compelling title\n'
        '- "content": The full narrative / messaging content\n'
        '- "key_messages": Array of 3-5 key message points\n'
        '- "talking_points": Array of 3-5 talking points (for leaders to use)\n'
        '- "recommended_vehicles": Array of recommended delivery channels\n\n'
        f'NARRATIVE TYPE: {narrative_type}\n'
        f'CONTEXT: {context}\n'
        f'{audience_context}\n'
        'Make it specific, inspiring, and actionable. Use a warm, authentic corporate tone.\n'
    )
    try:
        response = client.chat.completions.create(
            model=os.environ.get('OPENAI_MODEL', 'gpt-4o-mini'),
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.7,
            max_tokens=2500,
        )
        text = response.choices[0].message.content
        return json.loads(text)
    except Exception as e:
        return _fallback_narrative(narrative_type, context)


def _fallback_narrative(narrative_type, context):
    """Basic narrative without AI."""
    ntype = narrative_type.replace('_', ' ').title()
    short_ctx = context[:50] if context else 'our change journey'
    return {
        "title": f"{ntype}: {short_ctx}",
        "content": (
            f"This {narrative_type.replace('_', ' ')} outlines {context}. "
            f"Our approach is built on transparency, collaboration, and shared success."
        ),
        "key_messages": [
            "We are committed to making this change successful for everyone",
            "Your voice and input shape how we move forward",
            "Together we build a stronger, more resilient organisation"
        ],
        "talking_points": [
            "This change supports our strategic objectives",
            "We have a clear roadmap with defined milestones",
            "Support structures are in place for all impacted teams"
        ],
        "recommended_vehicles": ["Email", "Team meeting", "Town hall"]
    }
